import dataclasses
import hashlib
import logging
import os
import shutil
import subprocess
import threading
from abc import ABC, abstractmethod
from collections.abc import Hashable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Self, Union

import pathspec

from opendev.core.context_engineering.tools.lsp.util.compat import getstate, match_path
from opendev.core.context_engineering.tools.lsp import ls_types
from opendev.core.context_engineering.tools.lsp.ls_config import Language, LanguageServerConfig
from opendev.core.context_engineering.tools.lsp.ls_handler import SolidLanguageServerHandler
from opendev.core.context_engineering.tools.lsp.lsp_protocol_handler import lsp_types as LSPTypes
from opendev.core.context_engineering.tools.lsp.lsp_protocol_handler.lsp_types import (
    DocumentSymbol,
    SymbolInformation,
)
from opendev.core.context_engineering.tools.lsp.lsp_protocol_handler.server import (
    ProcessLaunchInfo,
    StringDict,
)
from opendev.core.context_engineering.tools.lsp.settings import SolidLSPSettings

# Import mixins
from opendev.core.context_engineering.tools.lsp.ls.file_ops import FileOpsMixin
from opendev.core.context_engineering.tools.lsp.ls.requests import RequestsMixin
from opendev.core.context_engineering.tools.lsp.ls.symbols import SymbolsMixin
from opendev.core.context_engineering.tools.lsp.ls.symbol_navigation import (
    SymbolNavigationMixin,
)
from opendev.core.context_engineering.tools.lsp.ls.cache import CacheMixin

GenericDocumentSymbol = Union[
    LSPTypes.DocumentSymbol, LSPTypes.SymbolInformation, ls_types.UnifiedSymbolInformation
]
log = logging.getLogger(__name__)


@dataclasses.dataclass(kw_only=True)
class ReferenceInSymbol:
    """A symbol retrieved when requesting reference to a symbol, together with the location of the reference"""

    symbol: ls_types.UnifiedSymbolInformation
    line: int
    character: int


@dataclasses.dataclass
class LSPFileBuffer:
    """
    This class is used to store the contents of an open LSP file in memory.
    """

    # uri of the file
    uri: str

    # The contents of the file
    contents: str

    # The version of the file
    version: int

    # The language id of the file
    language_id: str

    # reference count of the file
    ref_count: int

    content_hash: str = ""

    def __post_init__(self) -> None:
        self.content_hash = hashlib.md5(self.contents.encode("utf-8")).hexdigest()

    def split_lines(self) -> list[str]:
        """Splits the contents of the file into lines."""
        return self.contents.split("\n")


class DocumentSymbols:
    # IMPORTANT: Instances of this class are persisted in the high-level document symbol cache

    def __init__(self, root_symbols: list[ls_types.UnifiedSymbolInformation]):
        self.root_symbols = root_symbols
        self._all_symbols: list[ls_types.UnifiedSymbolInformation] | None = None

    def __getstate__(self) -> dict:
        return getstate(DocumentSymbols, self, transient_properties=["_all_symbols"])

    def iter_symbols(self) -> Iterator[ls_types.UnifiedSymbolInformation]:
        """
        Iterate over all symbols in the document symbol tree.
        Yields symbols in a depth-first manner.
        """
        if self._all_symbols is not None:
            yield from self._all_symbols
            return

        def traverse(
            s: ls_types.UnifiedSymbolInformation,
        ) -> Iterator[ls_types.UnifiedSymbolInformation]:
            yield s
            for child in s.get("children", []):
                yield from traverse(child)

        for root_symbol in self.root_symbols:
            yield from traverse(root_symbol)

    def get_all_symbols_and_roots(
        self,
    ) -> tuple[list[ls_types.UnifiedSymbolInformation], list[ls_types.UnifiedSymbolInformation]]:
        """
        This function returns all symbols in the document as a flat list and the root symbols.
        It exists to facilitate migration from previous versions, where this was the return interface of
        the LS method that obtained document symbols.

        :return: A tuple containing a list of all symbols in the document and a list of root symbols.
        """
        if self._all_symbols is None:
            self._all_symbols = list(self.iter_symbols())
        return self._all_symbols, self.root_symbols


class SolidLanguageServer(
    FileOpsMixin, RequestsMixin, SymbolsMixin, SymbolNavigationMixin, CacheMixin, ABC
):
    """
    The LanguageServer class provides a language agnostic interface to the Language Server Protocol.
    It is used to communicate with Language Servers of different programming languages.
    """

    CACHE_FOLDER_NAME = "cache"
    RAW_DOCUMENT_SYMBOLS_CACHE_VERSION = 1
    """
    global version identifier for raw symbol caches; an LS-specific version is defined separately and combined with this.
    This should be incremented whenever there is a change in the way raw document symbols are stored.
    If the result of a language server changes in a way that affects the raw document symbols,
    the LS-specific version should be incremented instead.
    """
    RAW_DOCUMENT_SYMBOL_CACHE_FILENAME = "raw_document_symbols.pkl"
    RAW_DOCUMENT_SYMBOL_CACHE_FILENAME_LEGACY_FALLBACK = "document_symbols_cache_v23-06-25.pkl"
    DOCUMENT_SYMBOL_CACHE_VERSION = 3
    DOCUMENT_SYMBOL_CACHE_FILENAME = "document_symbols.pkl"

    # To be overridden and extended by subclasses
    def is_ignored_dirname(self, dirname: str) -> bool:
        """
        A language-specific condition for directories that should always be ignored. For example, venv
        in Python and node_modules in JS/TS should be ignored always.
        """
        return dirname.startswith(".")

    @staticmethod
    def _determine_log_level(line: str) -> int:
        """
        Classify a stderr line from the language server to determine appropriate logging level.

        Language servers may emit informational messages to stderr that contain words like "error"
        but are not actual errors. Subclasses can override this method to filter out known
        false-positive patterns specific to their language server.

        :param line: The stderr line to classify
        :return: A logging level (logging.DEBUG, logging.INFO, logging.WARNING, or logging.ERROR)
        """
        line_lower = line.lower()

        # Default classification: treat lines with "error" or "exception" as ERROR level
        if "error" in line_lower or "exception" in line_lower or line.startswith("E["):
            return logging.ERROR
        else:
            return logging.INFO

    @classmethod
    def get_language_enum_instance(cls) -> Language:
        return Language.from_ls_class(cls)

    @classmethod
    def ls_resources_dir(cls, solidlsp_settings: SolidLSPSettings, mkdir: bool = True) -> str:
        """
        Returns the directory where the language server resources are downloaded.
        This is used to store language server binaries, configuration files, etc.
        """
        result = os.path.join(solidlsp_settings.ls_resources_dir, cls.__name__)

        # Migration of previously downloaded LS resources that were downloaded to a subdir of solidlsp instead of to the user's home
        pre_migration_ls_resources_dir = os.path.join(
            os.path.dirname(__file__), "language_servers", "static", cls.__name__
        )
        if os.path.exists(pre_migration_ls_resources_dir):
            if os.path.exists(result):
                # if the directory already exists, we just remove the old resources
                shutil.rmtree(result, ignore_errors=True)
            else:
                # move old resources to the new location
                shutil.move(pre_migration_ls_resources_dir, result)
        if mkdir:
            os.makedirs(result, exist_ok=True)
        return result

    @classmethod
    def create(
        cls,
        config: LanguageServerConfig,
        repository_root_path: str,
        timeout: float | None = None,
        solidlsp_settings: SolidLSPSettings | None = None,
    ) -> "SolidLanguageServer":
        """
        Creates a language specific LanguageServer instance based on the given configuration, and appropriate settings for the programming language.

        If language is Java, then ensure that jdk-17.0.6 or higher is installed, `java` is in PATH, and JAVA_HOME is set to the installation directory.
        If language is JS/TS, then ensure that node (v18.16.0 or higher) is installed and in PATH.

        :param repository_root_path: The root path of the repository.
        :param config: language server configuration.
        :param logger: The logger to use.
        :param timeout: the timeout for requests to the language server. If None, no timeout will be used.
        :param solidlsp_settings: additional settings
        :return LanguageServer: A language specific LanguageServer instance.
        """
        ls: SolidLanguageServer
        if solidlsp_settings is None:
            solidlsp_settings = SolidLSPSettings()

        ls_class = config.code_language.get_ls_class()
        # For now, we assume that all language server implementations have the same signature of the constructor
        # (which, unfortunately, differs from the signature of the base class).
        # If this assumption is ever violated, we need branching logic here.
        ls = ls_class(config, repository_root_path, solidlsp_settings)  # type: ignore
        ls.set_request_timeout(timeout)
        return ls

    def __init__(
        self,
        config: LanguageServerConfig,
        repository_root_path: str,
        process_launch_info: ProcessLaunchInfo,
        language_id: str,
        solidlsp_settings: SolidLSPSettings,
        cache_version_raw_document_symbols: Hashable = 1,
    ):
        """
        Initializes a LanguageServer instance.

        Do not instantiate this class directly. Use `LanguageServer.create` method instead.

        :param config: the global SolidLSP configuration.
        :param repository_root_path: the root path of the repository.
        :param process_launch_info: the command used to start the actual language server.
            The command must pass appropriate flags to the binary, so that it runs in the stdio mode,
            as opposed to HTTP, TCP modes supported by some language servers.
        :param cache_version_raw_document_symbols: the version, for caching, of the raw document symbols coming
            from this specific language server. This should be incremented by subclasses calling this constructor
            whenever the format of the raw document symbols changes (typically because the language server
            improves/fixes its output).
        """
        self._solidlsp_settings = solidlsp_settings
        lang = self.get_language_enum_instance()
        self._custom_settings = solidlsp_settings.get_ls_specific_settings(lang)
        log.debug(f"Custom config (LS-specific settings) for {lang}: {self._custom_settings}")
        self._encoding = config.encoding
        self.repository_root_path: str = repository_root_path
        log.debug(
            f"Creating language server instance for {repository_root_path=} with {language_id=} and process launch info: {process_launch_info}"
        )

        self.language_id = language_id
        self.open_file_buffers: dict[str, LSPFileBuffer] = {}
        self.language = Language(language_id)

        # initialise symbol caches
        self.cache_dir = (
            Path(self.repository_root_path)
            / self._solidlsp_settings.project_data_relative_path
            / self.CACHE_FOLDER_NAME
            / self.language_id
        )
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        # * raw document symbols cache
        self._ls_specific_raw_document_symbols_cache_version = cache_version_raw_document_symbols
        self._raw_document_symbols_cache: dict[
            str, tuple[str, list[DocumentSymbol] | list[SymbolInformation] | None]
        ] = {}
        """maps relative file paths to a tuple of (file_content_hash, raw_root_symbols)"""
        self._raw_document_symbols_cache_is_modified: bool = False
        self._load_raw_document_symbols_cache()
        # * high-level document symbols cache
        self._document_symbols_cache: dict[str, tuple[str, DocumentSymbols]] = {}
        """maps relative file paths to a tuple of (file_content_hash, document_symbols)"""
        self._document_symbols_cache_is_modified: bool = False
        self._load_document_symbols_cache()

        self.server_started = False
        self.completions_available = threading.Event()
        if config.trace_lsp_communication:

            def logging_fn(source: str, target: str, msg: StringDict | str) -> None:
                log.debug(f"LSP: {source} -> {target}: {msg!s}")

        else:
            logging_fn = None  # type: ignore

        # cmd is obtained from the child classes, which provide the language specific command to start the language server
        # LanguageServerHandler provides the functionality to start the language server and communicate with it
        log.debug(
            f"Creating language server instance with {language_id=} and process launch info: {process_launch_info}"
        )
        self.server = SolidLanguageServerHandler(
            process_launch_info,
            language=self.language,
            determine_log_level=self._determine_log_level,
            logger=logging_fn,
            start_independent_lsp_process=config.start_independent_lsp_process,
        )

        # Set up the pathspec matcher for the ignored paths
        # for all absolute paths in ignored_paths, convert them to relative paths
        processed_patterns = []
        for pattern in set(config.ignored_paths):
            # Normalize separators (pathspec expects forward slashes)
            pattern = pattern.replace(os.path.sep, "/")
            processed_patterns.append(pattern)
        log.debug(f"Processing {len(processed_patterns)} ignored paths from the config")

        # Create a pathspec matcher from the processed patterns
        self._ignore_spec = pathspec.PathSpec.from_lines(
            pathspec.patterns.GitWildMatchPattern, processed_patterns
        )

        self._request_timeout: float | None = None

        self._has_waited_for_cross_file_references = False

    def _get_wait_time_for_cross_file_referencing(self) -> float:
        """Meant to be overridden by subclasses for LS that don't have a reliable "finished initializing" signal.

        LS may return incomplete results on calls to `request_references` (only references found in the same file),
        if the LS is not fully initialized yet.
        """
        return 2

    def set_request_timeout(self, timeout: float | None) -> None:
        """
        :param timeout: the timeout, in seconds, for requests to the language server.
        """
        self.server.set_request_timeout(timeout)

    def get_ignore_spec(self) -> pathspec.PathSpec:
        """
        Returns the pathspec matcher for the paths that were configured to be ignored through
        the language server configuration.

        This is a subset of the full language-specific ignore spec that determines
        which files are relevant for the language server.

        This matcher is useful for operations outside of the language server,
        such as when searching for relevant non-language files in the project.
        """
        return self._ignore_spec

    def is_ignored_path(self, relative_path: str, ignore_unsupported_files: bool = True) -> bool:
        """
        Determine if a path should be ignored based on file type
        and ignore patterns.

        :param relative_path: Relative path to check
        :param ignore_unsupported_files: whether files that are not supported source files should be ignored

        :return: True if the path should be ignored, False otherwise
        """
        abs_path = os.path.join(self.repository_root_path, relative_path)
        if not os.path.exists(abs_path):
            raise FileNotFoundError(
                f"File {abs_path} not found, the ignore check cannot be performed"
            )

        # Check file extension if it's a file
        is_file = os.path.isfile(abs_path)
        if is_file and ignore_unsupported_files:
            fn_matcher = self.language.get_source_fn_matcher()
            if not fn_matcher.is_relevant_filename(abs_path):
                return True

        # Create normalized path for consistent handling
        rel_path = Path(relative_path)

        # Check each part of the path against always fulfilled ignore conditions
        dir_parts = rel_path.parts
        if is_file:
            dir_parts = dir_parts[:-1]
        for part in dir_parts:
            if not part:  # Skip empty parts (e.g., from leading '/')
                continue
            if self.is_ignored_dirname(part):
                return True

        return match_path(
            relative_path, self.get_ignore_spec(), root_path=self.repository_root_path
        )

    def _shutdown(self, timeout: float = 5.0) -> None:
        """
        A robust shutdown process designed to terminate cleanly on all platforms, including Windows,
        by explicitly closing all I/O pipes.
        """
        if not self.server.is_running():
            log.debug("Server process not running, skipping shutdown.")
            return

        log.info(f"Initiating final robust shutdown with a {timeout}s timeout...")
        process = self.server.process
        if process is None:
            log.debug("Server process is None, cannot shutdown.")
            return

        # --- Main Shutdown Logic ---
        # Stage 1: Graceful Termination Request
        # Send LSP shutdown and close stdin to signal no more input.
        try:
            log.debug("Sending LSP shutdown request...")
            # Use a thread to timeout the LSP shutdown call since it can hang
            shutdown_thread = threading.Thread(target=self.server.shutdown)
            shutdown_thread.daemon = True
            shutdown_thread.start()
            shutdown_thread.join(timeout=2.0)  # 2 second timeout for LSP shutdown

            if shutdown_thread.is_alive():
                log.debug("LSP shutdown request timed out, proceeding to terminate...")
            else:
                log.debug("LSP shutdown request completed.")

            if process.stdin and not process.stdin.closed:
                process.stdin.close()
            log.debug("Stage 1 shutdown complete.")
        except Exception as e:
            log.debug(f"Exception during graceful shutdown: {e}")
            # Ignore errors here, we are proceeding to terminate anyway.

        # Stage 2: Terminate and Wait for Process to Exit
        log.debug(f"Terminating process {process.pid}, current status: {process.poll()}")
        process.terminate()

        # Stage 3: Wait for process termination with timeout
        try:
            log.debug(f"Waiting for process {process.pid} to terminate...")
            exit_code = process.wait(timeout=timeout)
            log.info(f"Language server process terminated successfully with exit code {exit_code}.")
        except subprocess.TimeoutExpired:
            # If termination failed, forcefully kill the process
            log.warning(
                f"Process {process.pid} termination timed out, killing process forcefully..."
            )
            process.kill()
            try:
                exit_code = process.wait(timeout=2.0)
                log.info(f"Language server process killed successfully with exit code {exit_code}.")
            except subprocess.TimeoutExpired:
                log.error(f"Process {process.pid} could not be killed within timeout.")
        except Exception as e:
            log.error(f"Error during process shutdown: {e}")

    @contextmanager
    def start_server(self) -> Iterator["SolidLanguageServer"]:
        self.start()
        yield self
        self.stop()

    def _start_server_process(self) -> None:
        self.server_started = True
        self._start_server()

    @abstractmethod
    def _start_server(self) -> None:
        pass

    def start(self) -> "SolidLanguageServer":
        """
        Starts the language server process and connects to it. Call shutdown when ready.

        :return: self for method chaining
        """
        log.info(
            f"Starting language server with language {self.language_server.language} for {self.language_server.repository_root_path}"
        )
        self._start_server_process()
        return self

    def stop(self, shutdown_timeout: float = 2.0) -> None:
        """
        Stops the language server process.
        This function never raises an exception (any exceptions during shutdown are logged).

        :param shutdown_timeout: time, in seconds, to wait for the server to shutdown gracefully before killing it
        """
        try:
            self._shutdown(timeout=shutdown_timeout)
        except Exception as e:
            log.warning(f"Exception while shutting down language server: {e}")

    @property
    def language_server(self) -> Self:
        return self

    def is_running(self) -> bool:
        return self.server.is_running()
