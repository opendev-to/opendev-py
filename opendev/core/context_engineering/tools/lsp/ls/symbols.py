from __future__ import annotations

import logging
import os
import pathlib
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, Union, cast

from opendev.core.context_engineering.tools.lsp import ls_types
from opendev.core.context_engineering.tools.lsp.ls_types import UnifiedSymbolInformation
from opendev.core.context_engineering.tools.lsp.lsp_protocol_handler import lsp_types as LSPTypes
from opendev.core.context_engineering.tools.lsp.lsp_protocol_handler.lsp_types import (
    DocumentSymbol,
    SymbolInformation,
)

if TYPE_CHECKING:
    from opendev.core.context_engineering.tools.lsp.ls.server import DocumentSymbols, LSPFileBuffer

GenericDocumentSymbol = Union[
    LSPTypes.DocumentSymbol, LSPTypes.SymbolInformation, ls_types.UnifiedSymbolInformation
]

log = logging.getLogger(__name__)


class SymbolsMixin:
    """Mixin providing document symbols, full symbol tree, and overview endpoints."""

    def _request_document_symbols(
        self, relative_file_path: str, file_data: LSPFileBuffer | None
    ) -> list[SymbolInformation] | list[DocumentSymbol] | None:
        """
        Sends a [documentSymbol](https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/#textDocument_documentSymbol)
        request to the language server to find symbols in the given file - or returns a cached result if available.

        :param relative_file_path: the relative path of the file that has the symbols.
        :param file_data: the file data buffer, if already opened. If None, the file will be opened in this method.
        :return: the list of root symbols in the file.
        """

        def get_cached_raw_document_symbols(
            cache_key: str, fd: LSPFileBuffer
        ) -> list[SymbolInformation] | list[DocumentSymbol] | None:
            file_hash_and_result = self._raw_document_symbols_cache.get(cache_key)
            if file_hash_and_result is not None:
                file_hash, result = file_hash_and_result
                if file_hash == fd.content_hash:
                    log.debug("Returning cached raw document symbols for %s", relative_file_path)
                    return result
                else:
                    log.debug(
                        "Document content for %s has changed (raw symbol cache is not up-to-date)",
                        relative_file_path,
                    )
            else:
                log.debug("No cache hit for raw document symbols symbols in %s", relative_file_path)
            return None

        def get_raw_document_symbols(
            fd: LSPFileBuffer,
        ) -> list[SymbolInformation] | list[DocumentSymbol] | None:
            # check for cached result
            cache_key = relative_file_path
            response = get_cached_raw_document_symbols(cache_key, fd)
            if response is not None:
                return response

            # no cached result, query language server
            log.debug(
                f"Requesting document symbols for {relative_file_path} from the Language Server"
            )
            response = self.server.send.document_symbol(
                {
                    "textDocument": {
                        "uri": pathlib.Path(
                            os.path.join(self.repository_root_path, relative_file_path)
                        ).as_uri()
                    }
                }
            )

            # update cache
            self._raw_document_symbols_cache[cache_key] = (fd.content_hash, response)
            self._raw_document_symbols_cache_is_modified = True

            return response

        if file_data is not None:
            return get_raw_document_symbols(file_data)
        else:
            with self.open_file(relative_file_path) as opened_file_data:
                return get_raw_document_symbols(opened_file_data)

    def request_document_symbols(
        self, relative_file_path: str, file_buffer: LSPFileBuffer | None = None
    ) -> DocumentSymbols:
        """
        Retrieves the collection of symbols in the given file

        :param relative_file_path: The relative path of the file that has the symbols
        :param file_buffer: an optional file buffer if the file is already opened.
        :return: the collection of symbols in the file.
            All contained symbols will have a location, children, and a parent attribute,
            where the parent attribute is None for root symbols.
            Note that this is slightly different from the call to request_full_symbol_tree,
            where the parent attribute will be the file symbol which in turn may have a package symbol as parent.
            If you need a symbol tree that contains file symbols as well, you should use `request_full_symbol_tree` instead.
        """
        from opendev.core.context_engineering.tools.lsp.ls.server import DocumentSymbols

        with self._open_file_context(relative_file_path, file_buffer) as file_data:
            # check if the desired result is cached
            cache_key = relative_file_path
            file_hash_and_result = self._document_symbols_cache.get(cache_key)
            if file_hash_and_result is not None:
                file_hash, document_symbols = file_hash_and_result
                if file_hash == file_data.content_hash:
                    log.debug("Returning cached document symbols for %s", relative_file_path)
                    return document_symbols
                else:
                    log.debug(
                        "Cached document symbol content for %s has changed", relative_file_path
                    )
            else:
                log.debug("No cache hit for document symbols in %s", relative_file_path)

            # no cached result: request the root symbols from the language server
            root_symbols = self._request_document_symbols(relative_file_path, file_data)

            if root_symbols is None:
                log.warning(
                    f"Received None response from the Language Server for document symbols in {relative_file_path}. "
                    f"This means the language server can't understand this file (possibly due to syntax errors). It may also be due to a bug or misconfiguration of the LS. "
                    f"Returning empty list",
                )
                return DocumentSymbols([])

            assert isinstance(
                root_symbols, list
            ), f"Unexpected response from Language Server: {root_symbols}"
            log.debug(
                "Received %d root symbols for %s from the language server",
                len(root_symbols),
                relative_file_path,
            )

            file_lines = file_data.split_lines()

            def convert_to_unified_symbol(
                original_symbol_dict: GenericDocumentSymbol,
            ) -> ls_types.UnifiedSymbolInformation:
                """
                Converts the given symbol dictionary to the unified representation, ensuring
                that all required fields are present (except 'children' which is handled separately).

                :param original_symbol_dict: the item to augment
                :return: the augmented item (new object)
                """
                # noinspection PyInvalidCast
                item = cast(ls_types.UnifiedSymbolInformation, dict(original_symbol_dict))
                absolute_path = os.path.join(self.repository_root_path, relative_file_path)

                # handle missing location and path entries
                if "location" not in item:
                    uri = pathlib.Path(absolute_path).as_uri()
                    assert "range" in item
                    tree_location = ls_types.Location(
                        uri=uri,
                        range=item["range"],
                        absolutePath=absolute_path,
                        relativePath=relative_file_path,
                    )
                    item["location"] = tree_location
                location = item["location"]
                if "absolutePath" not in location:
                    location["absolutePath"] = absolute_path  # type: ignore
                if "relativePath" not in location:
                    location["relativePath"] = relative_file_path  # type: ignore

                if "body" not in item:
                    item["body"] = self.retrieve_symbol_body(item, file_lines=file_lines)

                # handle missing selectionRange
                if "selectionRange" not in item:
                    if "range" in item:
                        item["selectionRange"] = item["range"]
                    else:
                        item["selectionRange"] = item["location"]["range"]

                return item

            def convert_symbols_with_common_parent(
                symbols: (
                    list[DocumentSymbol] | list[SymbolInformation] | list[UnifiedSymbolInformation]
                ),
                parent: ls_types.UnifiedSymbolInformation | None,
            ) -> list[ls_types.UnifiedSymbolInformation]:
                """
                Converts the given symbols into UnifiedSymbolInformation with proper parent-child relationships,
                adding overload indices for symbols with the same name under the same parent.
                """
                total_name_counts: dict[str, int] = defaultdict(lambda: 0)
                for symbol in symbols:
                    total_name_counts[symbol["name"]] += 1
                name_counts: dict[str, int] = defaultdict(lambda: 0)
                unified_symbols = []
                for symbol in symbols:
                    usymbol = convert_to_unified_symbol(symbol)
                    if total_name_counts[usymbol["name"]] > 1:
                        usymbol["overload_idx"] = name_counts[usymbol["name"]]
                    name_counts[usymbol["name"]] += 1
                    usymbol["parent"] = parent
                    if "children" in usymbol:
                        usymbol["children"] = convert_symbols_with_common_parent(usymbol["children"], usymbol)  # type: ignore
                    else:
                        usymbol["children"] = []  # type: ignore
                    unified_symbols.append(usymbol)
                return unified_symbols

            unified_root_symbols = convert_symbols_with_common_parent(root_symbols, None)
            document_symbols = DocumentSymbols(unified_root_symbols)

            # update cache
            log.debug("Updating cached document symbols for %s", relative_file_path)
            self._document_symbols_cache[cache_key] = (file_data.content_hash, document_symbols)
            self._document_symbols_cache_is_modified = True

            return document_symbols

    def request_full_symbol_tree(
        self, within_relative_path: str | None = None
    ) -> list[ls_types.UnifiedSymbolInformation]:
        """
        Will go through all files in the project or within a relative path and build a tree of symbols.
        Note: this may be slow the first time it is called, especially if `within_relative_path` is not used to restrict the search.

        For each file, a symbol of kind File (2) will be created. For directories, a symbol of kind Package (4) will be created.
        All symbols will have a children attribute, thereby representing the tree structure of all symbols in the project
        that are within the repository.
        All symbols except the root packages will have a parent attribute.
        Will ignore directories starting with '.', language-specific defaults
        and user-configured directories (e.g. from .gitignore).

        :param within_relative_path: pass a relative path to only consider symbols within this path.
            If a file is passed, only the symbols within this file will be considered.
            If a directory is passed, all files within this directory will be considered.
        :return: A list of root symbols representing the top-level packages/modules in the project.
        """
        if within_relative_path is not None:
            within_abs_path = os.path.join(self.repository_root_path, within_relative_path)
            if not os.path.exists(within_abs_path):
                raise FileNotFoundError(f"File or directory not found: {within_abs_path}")
            if os.path.isfile(within_abs_path):
                if self.is_ignored_path(within_relative_path):
                    log.error(
                        "You passed a file explicitly, but it is ignored. This is probably an error. File: %s",
                        within_relative_path,
                    )
                    return []
                else:
                    root_nodes = self.request_document_symbols(within_relative_path).root_symbols
                    return root_nodes

        # Helper function to recursively process directories
        def process_directory(rel_dir_path: str) -> list[ls_types.UnifiedSymbolInformation]:
            abs_dir_path = (
                self.repository_root_path
                if rel_dir_path == "."
                else os.path.join(self.repository_root_path, rel_dir_path)
            )
            abs_dir_path = os.path.realpath(abs_dir_path)

            if self.is_ignored_path(str(Path(abs_dir_path).relative_to(self.repository_root_path))):
                log.debug("Skipping directory: %s (because it should be ignored)", rel_dir_path)
                return []

            result = []
            try:
                contained_dir_or_file_names = os.listdir(abs_dir_path)
            except OSError:
                return []

            # Create package symbol for directory
            package_symbol = ls_types.UnifiedSymbolInformation(  # type: ignore
                name=os.path.basename(abs_dir_path),
                kind=ls_types.SymbolKind.Package,
                location=ls_types.Location(
                    uri=str(pathlib.Path(abs_dir_path).as_uri()),
                    range={
                        "start": {"line": 0, "character": 0},
                        "end": {"line": 0, "character": 0},
                    },
                    absolutePath=str(abs_dir_path),
                    relativePath=str(
                        Path(abs_dir_path).resolve().relative_to(self.repository_root_path)
                    ),
                ),
                children=[],
            )
            result.append(package_symbol)

            for contained_dir_or_file_name in contained_dir_or_file_names:
                contained_dir_or_file_abs_path = os.path.join(
                    abs_dir_path, contained_dir_or_file_name
                )

                # obtain relative path
                try:
                    contained_dir_or_file_rel_path = str(
                        Path(contained_dir_or_file_abs_path)
                        .resolve()
                        .relative_to(self.repository_root_path)
                    )
                except ValueError as e:
                    # Typically happens when the path is not under the repository root (e.g., symlink pointing outside)
                    log.warning(
                        "Skipping path %s; likely outside of the repository root %s [cause: %s]",
                        contained_dir_or_file_abs_path,
                        self.repository_root_path,
                        e,
                    )
                    continue

                if self.is_ignored_path(contained_dir_or_file_rel_path):
                    log.debug(
                        "Skipping item: %s (because it should be ignored)",
                        contained_dir_or_file_rel_path,
                    )
                    continue

                if os.path.isdir(contained_dir_or_file_abs_path):
                    child_symbols = process_directory(contained_dir_or_file_rel_path)
                    package_symbol["children"].extend(child_symbols)
                    for child in child_symbols:
                        child["parent"] = package_symbol

                elif os.path.isfile(contained_dir_or_file_abs_path):
                    with self._open_file_context(contained_dir_or_file_rel_path) as file_data:
                        document_symbols = self.request_document_symbols(
                            contained_dir_or_file_rel_path, file_data
                        )
                        file_root_nodes = document_symbols.root_symbols

                        # Create file symbol, link with children
                        file_range = self._get_range_from_file_content(file_data.contents)
                        file_symbol = ls_types.UnifiedSymbolInformation(  # type: ignore
                            name=os.path.splitext(contained_dir_or_file_name)[0],
                            kind=ls_types.SymbolKind.File,
                            range=file_range,
                            selectionRange=file_range,
                            location=ls_types.Location(
                                uri=str(pathlib.Path(contained_dir_or_file_abs_path).as_uri()),
                                range=file_range,
                                absolutePath=str(contained_dir_or_file_abs_path),
                                relativePath=str(
                                    Path(contained_dir_or_file_abs_path)
                                    .resolve()
                                    .relative_to(self.repository_root_path)
                                ),
                            ),
                            children=file_root_nodes,
                            parent=package_symbol,
                        )
                        for child in file_root_nodes:
                            child["parent"] = file_symbol

                    # Link file symbol with package
                    package_symbol["children"].append(file_symbol)

                    # TODO: Not sure if this is actually still needed given recent changes to relative path handling
                    def fix_relative_path(nodes: list[ls_types.UnifiedSymbolInformation]) -> None:
                        for node in nodes:
                            if "location" in node and "relativePath" in node["location"]:
                                path = Path(node["location"]["relativePath"])  # type: ignore
                                if path.is_absolute():
                                    try:
                                        path = path.relative_to(self.repository_root_path)
                                        node["location"]["relativePath"] = str(path)
                                    except Exception:
                                        pass
                            if "children" in node:
                                fix_relative_path(node["children"])

                    fix_relative_path(file_root_nodes)

            return result

        # Start from the root or the specified directory
        start_rel_path = within_relative_path or "."
        return process_directory(start_rel_path)

    @staticmethod
    def _get_range_from_file_content(file_content: str) -> ls_types.Range:
        """
        Get the range for the given file.
        """
        lines = file_content.split("\n")
        end_line = len(lines)
        end_column = len(lines[-1])
        return ls_types.Range(
            start=ls_types.Position(line=0, character=0),
            end=ls_types.Position(line=end_line, character=end_column),
        )

    def request_dir_overview(
        self, relative_dir_path: str
    ) -> dict[str, list[UnifiedSymbolInformation]]:
        """
        :return: A mapping of all relative paths analyzed to lists of top-level symbols in the corresponding file.
        """
        symbol_tree = self.request_full_symbol_tree(relative_dir_path)
        # Initialize result dictionary
        result: dict[str, list[UnifiedSymbolInformation]] = defaultdict(list)

        # Helper function to process a symbol and its children
        def process_symbol(symbol: ls_types.UnifiedSymbolInformation) -> None:
            if symbol["kind"] == ls_types.SymbolKind.File:
                # For file symbols, process their children (top-level symbols)
                for child in symbol["children"]:
                    # Handle cross-platform path resolution (fixes Docker/macOS path issues)
                    absolute_path = Path(child["location"]["absolutePath"]).resolve()
                    repository_root = Path(self.repository_root_path).resolve()

                    # Try pathlib first, fallback to alternative approach if paths are incompatible
                    try:
                        path = absolute_path.relative_to(repository_root)
                    except ValueError:
                        # If paths are from different roots (e.g., /workspaces vs /Users),
                        # use the relativePath from location if available, or extract from absolutePath
                        if (
                            "relativePath" in child["location"]
                            and child["location"]["relativePath"]
                        ):
                            path = Path(child["location"]["relativePath"])
                        else:
                            # Extract relative path by finding common structure
                            # Example: /workspaces/.../test_repo/file.py -> test_repo/file.py
                            path_parts = absolute_path.parts

                            # Find the last common part or use a fallback
                            if "test_repo" in path_parts:
                                test_repo_idx = path_parts.index("test_repo")
                                path = Path(*path_parts[test_repo_idx:])
                            else:
                                # Last resort: use filename only
                                path = Path(absolute_path.name)
                    result[str(path)].append(child)
            # For package/directory symbols, process their children
            for child in symbol["children"]:
                process_symbol(child)

        # Process each root symbol
        for root in symbol_tree:
            process_symbol(root)
        return result

    def request_document_overview(self, relative_file_path: str) -> list[UnifiedSymbolInformation]:
        """
        :return: the top-level symbols in the given file.
        """
        return self.request_document_symbols(relative_file_path).root_symbols

    def request_overview(
        self, within_relative_path: str
    ) -> dict[str, list[UnifiedSymbolInformation]]:
        """
        An overview of all symbols in the given file or directory.

        :param within_relative_path: the relative path to the file or directory to get the overview of.
        :return: A mapping of all relative paths analyzed to lists of top-level symbols in the corresponding file.
        """
        abs_path = (Path(self.repository_root_path) / within_relative_path).resolve()
        if not abs_path.exists():
            raise FileNotFoundError(f"File or directory not found: {abs_path}")

        if abs_path.is_file():
            symbols_overview = self.request_document_overview(within_relative_path)
            return {within_relative_path: symbols_overview}
        else:
            return self.request_dir_overview(within_relative_path)
