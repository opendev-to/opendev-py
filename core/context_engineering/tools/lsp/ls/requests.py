from __future__ import annotations

import json
import logging
import os
import pathlib
from pathlib import Path, PurePath
from time import sleep
from typing import TYPE_CHECKING, cast

from opendev.core.context_engineering.tools.lsp import ls_types
from opendev.core.context_engineering.tools.lsp.ls_exceptions import SolidLSPException
from opendev.core.context_engineering.tools.lsp.ls_utils import PathUtils
from opendev.core.context_engineering.tools.lsp.lsp_protocol_handler import lsp_types as LSPTypes
from opendev.core.context_engineering.tools.lsp.lsp_protocol_handler.lsp_constants import (
    LSPConstants,
)
from opendev.core.context_engineering.tools.lsp.lsp_protocol_handler.lsp_types import (
    Definition,
    DefinitionParams,
    LocationLink,
    RenameParams,
)
from opendev.core.context_engineering.tools.lsp.lsp_protocol_handler.server import LSPError

if TYPE_CHECKING:
    from opendev.core.context_engineering.tools.lsp.lsp_protocol_handler import lsp_types

log = logging.getLogger(__name__)


class RequestsMixin:
    """Mixin providing LSP request methods: definition, references, diagnostics, completions, hover, workspace, rename, text edits."""

    def _send_definition_request(
        self, definition_params: DefinitionParams
    ) -> Definition | list[LocationLink] | None:
        return self.server.send.definition(definition_params)

    def request_definition(
        self, relative_file_path: str, line: int, column: int
    ) -> list[ls_types.Location]:
        """
        Raise a [textDocument/definition](https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/#textDocument_definition) request to the Language Server
        for the symbol at the given line and column in the given file. Wait for the response and return the result.

        :param relative_file_path: The relative path of the file that has the symbol for which definition should be looked up
        :param line: The line number of the symbol
        :param column: The column number of the symbol

        :return: the list of locations where the symbol is defined
        """
        if not self.server_started:
            log.error("request_definition called before language server started")
            raise SolidLSPException("Language Server not started")

        if not self._has_waited_for_cross_file_references:
            # Some LS require waiting for a while before they can return cross-file definitions.
            # This is a workaround for such LS that don't have a reliable "finished initializing" signal.
            sleep(self._get_wait_time_for_cross_file_referencing())
            self._has_waited_for_cross_file_references = True

        with self.open_file(relative_file_path):
            # sending request to the language server and waiting for response
            definition_params = cast(
                DefinitionParams,
                {
                    LSPConstants.TEXT_DOCUMENT: {
                        LSPConstants.URI: pathlib.Path(
                            str(PurePath(self.repository_root_path, relative_file_path))
                        ).as_uri()
                    },
                    LSPConstants.POSITION: {
                        LSPConstants.LINE: line,
                        LSPConstants.CHARACTER: column,
                    },
                },
            )
            response = self._send_definition_request(definition_params)

        ret: list[ls_types.Location] = []
        if isinstance(response, list):
            # response is either of type Location[] or LocationLink[]
            for item in response:
                assert isinstance(item, dict)
                if LSPConstants.URI in item and LSPConstants.RANGE in item:
                    new_item: dict = {}
                    new_item.update(item)
                    new_item["absolutePath"] = PathUtils.uri_to_path(new_item["uri"])
                    new_item["relativePath"] = PathUtils.get_relative_path(
                        new_item["absolutePath"], self.repository_root_path
                    )
                    ret.append(ls_types.Location(**new_item))  # type: ignore
                elif (
                    LSPConstants.TARGET_URI in item
                    and LSPConstants.TARGET_RANGE in item
                    and LSPConstants.TARGET_SELECTION_RANGE in item
                ):
                    new_item: dict = {}  # type: ignore
                    new_item["uri"] = item[LSPConstants.TARGET_URI]  # type: ignore
                    new_item["absolutePath"] = PathUtils.uri_to_path(new_item["uri"])
                    new_item["relativePath"] = PathUtils.get_relative_path(
                        new_item["absolutePath"], self.repository_root_path
                    )
                    new_item["range"] = item[LSPConstants.TARGET_SELECTION_RANGE]  # type: ignore
                    ret.append(ls_types.Location(**new_item))  # type: ignore
                else:
                    assert False, f"Unexpected response from Language Server: {item}"
        elif isinstance(response, dict):
            # response is of type Location
            assert LSPConstants.URI in response
            assert LSPConstants.RANGE in response

            new_item: dict = {}  # type: ignore
            new_item.update(response)
            new_item["absolutePath"] = PathUtils.uri_to_path(new_item["uri"])
            new_item["relativePath"] = PathUtils.get_relative_path(
                new_item["absolutePath"], self.repository_root_path
            )
            ret.append(ls_types.Location(**new_item))  # type: ignore
        elif response is None:
            # Some language servers return None when they cannot find a definition
            # This is expected for certain symbol types like generics or types with incomplete information
            log.warning(
                f"Language server returned None for definition request at {relative_file_path}:{line}:{column}"
            )
        else:
            assert False, f"Unexpected response from Language Server: {response}"

        return ret

    # Some LS cause problems with this, so the call is isolated from the rest to allow overriding in subclasses
    def _send_references_request(
        self, relative_file_path: str, line: int, column: int
    ) -> list[lsp_types.Location] | None:
        return self.server.send.references(
            {
                "textDocument": {
                    "uri": PathUtils.path_to_uri(
                        os.path.join(self.repository_root_path, relative_file_path)
                    )
                },
                "position": {"line": line, "character": column},
                "context": {"includeDeclaration": False},
            }
        )

    def request_references(
        self, relative_file_path: str, line: int, column: int
    ) -> list[ls_types.Location]:
        """
        Raise a [textDocument/references](https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/#textDocument_references) request to the Language Server
        to find references to the symbol at the given line and column in the given file. Wait for the response and return the result.
        Filters out references located in ignored directories.

        :param relative_file_path: The relative path of the file that has the symbol for which references should be looked up
        :param line: The line number of the symbol
        :param column: The column number of the symbol

        :return: A list of locations where the symbol is referenced (excluding ignored directories)
        """
        if not self.server_started:
            log.error("request_references called before Language Server started")
            raise SolidLSPException("Language Server not started")

        if not self._has_waited_for_cross_file_references:
            # Some LS require waiting for a while before they can return cross-file references.
            # This is a workaround for such LS that don't have a reliable "finished initializing" signal.
            sleep(self._get_wait_time_for_cross_file_referencing())
            self._has_waited_for_cross_file_references = True

        with self.open_file(relative_file_path):
            try:
                response = self._send_references_request(
                    relative_file_path, line=line, column=column
                )
            except Exception as e:
                # Catch LSP internal error (-32603) and raise a more informative exception
                if isinstance(e, LSPError) and getattr(e, "code", None) == -32603:
                    raise RuntimeError(
                        f"LSP internal error (-32603) when requesting references for {relative_file_path}:{line}:{column}. "
                        "This often occurs when requesting references for a symbol not referenced in the expected way. "
                    ) from e
                raise
        if response is None:
            return []

        ret: list[ls_types.Location] = []
        assert isinstance(
            response, list
        ), f"Unexpected response from Language Server (expected list, got {type(response)}): {response}"
        for item in response:
            assert isinstance(
                item, dict
            ), f"Unexpected response from Language Server (expected dict, got {type(item)}): {item}"
            assert LSPConstants.URI in item
            assert LSPConstants.RANGE in item

            abs_path = PathUtils.uri_to_path(item[LSPConstants.URI])  # type: ignore
            if not Path(abs_path).is_relative_to(self.repository_root_path):
                log.warning(
                    "Found a reference in a path outside the repository, probably the LS is parsing things in installed packages or in the standardlib! "
                    f"Path: {abs_path}. This is a bug but we currently simply skip these references."
                )
                continue

            rel_path = Path(abs_path).relative_to(self.repository_root_path)
            if self.is_ignored_path(str(rel_path)):
                log.debug("Ignoring reference in %s since it should be ignored", rel_path)
                continue

            new_item: dict = {}
            new_item.update(item)
            new_item["absolutePath"] = str(abs_path)
            new_item["relativePath"] = str(rel_path)
            ret.append(ls_types.Location(**new_item))  # type: ignore

        return ret

    def request_text_document_diagnostics(
        self, relative_file_path: str
    ) -> list[ls_types.Diagnostic]:
        """
        Raise a [textDocument/diagnostic](https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/#textDocument_diagnostic) request to the Language Server
        to find diagnostics for the given file. Wait for the response and return the result.

        :param relative_file_path: The relative path of the file to retrieve diagnostics for

        :return: A list of diagnostics for the file
        """
        if not self.server_started:
            log.error("request_text_document_diagnostics called before Language Server started")
            raise SolidLSPException("Language Server not started")

        with self.open_file(relative_file_path):
            response = self.server.send.text_document_diagnostic(
                {
                    LSPConstants.TEXT_DOCUMENT: {  # type: ignore
                        LSPConstants.URI: pathlib.Path(
                            str(PurePath(self.repository_root_path, relative_file_path))
                        ).as_uri()
                    }
                }
            )

        if response is None:
            return []  # type: ignore

        assert isinstance(
            response, dict
        ), f"Unexpected response from Language Server (expected list, got {type(response)}): {response}"
        ret: list[ls_types.Diagnostic] = []
        for item in response["items"]:  # type: ignore
            new_item: ls_types.Diagnostic = {
                "uri": pathlib.Path(
                    str(PurePath(self.repository_root_path, relative_file_path))
                ).as_uri(),
                "severity": item["severity"],
                "message": item["message"],
                "range": item["range"],
                "code": item["code"],  # type: ignore
            }
            ret.append(ls_types.Diagnostic(**new_item))

        return ret

    def request_completions(
        self, relative_file_path: str, line: int, column: int, allow_incomplete: bool = False
    ) -> list[ls_types.CompletionItem]:
        """
        Raise a [textDocument/completion](https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/#textDocument_completion) request to the Language Server
        to find completions at the given line and column in the given file. Wait for the response and return the result.

        :param relative_file_path: The relative path of the file that has the symbol for which completions should be looked up
        :param line: The line number of the symbol
        :param column: The column number of the symbol

        :return: A list of completions
        """
        with self.open_file(relative_file_path):
            open_file_buffer = self.open_file_buffers[
                pathlib.Path(os.path.join(self.repository_root_path, relative_file_path)).as_uri()
            ]
            completion_params: LSPTypes.CompletionParams = {
                "position": {"line": line, "character": column},
                "textDocument": {"uri": open_file_buffer.uri},
                "context": {"triggerKind": LSPTypes.CompletionTriggerKind.Invoked},
            }
            response: list[LSPTypes.CompletionItem] | LSPTypes.CompletionList | None = None

            num_retries = 0
            while response is None or (response["isIncomplete"] and num_retries < 30):  # type: ignore
                self.completions_available.wait()
                response = self.server.send.completion(completion_params)
                if isinstance(response, list):
                    response = {"items": response, "isIncomplete": False}
                num_retries += 1

            # TODO: Understand how to appropriately handle `isIncomplete`
            if response is None or (response["isIncomplete"] and not allow_incomplete):  # type: ignore
                return []

            if "items" in response:
                response = response["items"]  # type: ignore

            response = cast(list[LSPTypes.CompletionItem], response)

            items = response

            completions_list: list[ls_types.CompletionItem] = []

            for item in items:
                assert "label" in item or "insertText" in item or "textEdit" in item
                assert "kind" in item
                completion_item = {}
                if "detail" in item:
                    completion_item["detail"] = item["detail"]

                if "textEdit" in item and "newText" in item["textEdit"]:
                    completion_item["completionText"] = item["textEdit"]["newText"]
                    completion_item["kind"] = item["kind"]
                elif "textEdit" in item and "range" in item["textEdit"]:
                    new_dot_lineno, new_dot_colno = (
                        completion_params["position"]["line"],
                        completion_params["position"]["character"],
                    )
                    assert all(
                        (
                            item["textEdit"]["range"]["start"]["line"] == new_dot_lineno,
                            item["textEdit"]["range"]["start"]["character"] == new_dot_colno,
                            item["textEdit"]["range"]["start"]["line"]
                            == item["textEdit"]["range"]["end"]["line"],
                            item["textEdit"]["range"]["start"]["character"]
                            == item["textEdit"]["range"]["end"]["character"],
                        )
                    )

                    completion_item["completionText"] = item["textEdit"]["newText"]
                    completion_item["kind"] = item["kind"]
                elif "textEdit" in item and "insert" in item["textEdit"]:
                    assert False
                elif "insertText" in item:  # type: ignore
                    completion_item["completionText"] = item["insertText"]
                    completion_item["kind"] = item["kind"]
                elif "label" in item:
                    completion_item["completionText"] = item["label"]
                    completion_item["kind"] = item["kind"]  # type: ignore
                else:
                    assert False

                completion_item = ls_types.CompletionItem(**completion_item)  # type: ignore
                completions_list.append(completion_item)

            return [
                json.loads(json_repr)
                for json_repr in set(json.dumps(item, sort_keys=True) for item in completions_list)
            ]

    def request_hover(
        self, relative_file_path: str, line: int, column: int
    ) -> ls_types.Hover | None:
        """
        Raise a [textDocument/hover](https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/#textDocument_hover) request to the Language Server
        to find the hover information at the given line and column in the given file. Wait for the response and return the result.

        :param relative_file_path: The relative path of the file that has the hover information
        :param line: The line number of the symbol
        :param column: The column number of the symbol

        :return None
        """
        with self.open_file(relative_file_path):
            response = self.server.send.hover(
                {
                    "textDocument": {
                        "uri": pathlib.Path(
                            os.path.join(self.repository_root_path, relative_file_path)
                        ).as_uri()
                    },
                    "position": {
                        "line": line,
                        "character": column,
                    },
                }
            )

        if response is None:
            return None

        assert isinstance(response, dict)

        return ls_types.Hover(**response)  # type: ignore

    def request_workspace_symbol(
        self, query: str
    ) -> list[ls_types.UnifiedSymbolInformation] | None:
        """
        Raise a [workspace/symbol](https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/#workspace_symbol) request to the Language Server
        to find symbols across the whole workspace. Wait for the response and return the result.

        :param query: The query string to filter symbols by

        :return: A list of matching symbols
        """
        response = self.server.send.workspace_symbol({"query": query})
        if response is None:
            return None

        assert isinstance(response, list)

        ret: list[ls_types.UnifiedSymbolInformation] = []
        for item in response:
            assert isinstance(item, dict)

            assert LSPConstants.NAME in item
            assert LSPConstants.KIND in item
            assert LSPConstants.LOCATION in item

            ret.append(ls_types.UnifiedSymbolInformation(**item))  # type: ignore

        return ret

    def request_rename_symbol_edit(
        self,
        relative_file_path: str,
        line: int,
        column: int,
        new_name: str,
    ) -> ls_types.WorkspaceEdit | None:
        """
        Retrieve a WorkspaceEdit for renaming the symbol at the given location to the new name.
        Does not apply the edit, just retrieves it. In order to actually rename the symbol, call apply_workspace_edit.

        :param relative_file_path: The relative path to the file containing the symbol
        :param line: The 0-indexed line number of the symbol
        :param column: The 0-indexed column number of the symbol
        :param new_name: The new name for the symbol
        :return: A WorkspaceEdit containing the changes needed to rename the symbol, or None if rename is not supported
        """
        params = RenameParams(
            textDocument=ls_types.TextDocumentIdentifier(
                uri=pathlib.Path(
                    os.path.join(self.repository_root_path, relative_file_path)
                ).as_uri()
            ),
            position=ls_types.Position(line=line, character=column),
            newName=new_name,
        )

        return self.server.send.rename(params)

    def apply_text_edits_to_file(self, relative_path: str, edits: list[ls_types.TextEdit]) -> None:
        """
        Apply a list of text edits to a file.

        :param relative_path: The relative path of the file to edit
        :param edits: List of TextEdit dictionaries to apply
        """
        with self.open_file(relative_path):
            # Sort edits by position (latest first) to avoid position shifts
            sorted_edits = sorted(
                edits,
                key=lambda e: (e["range"]["start"]["line"], e["range"]["start"]["character"]),
                reverse=True,
            )

            for edit in sorted_edits:
                start_pos = ls_types.Position(
                    line=edit["range"]["start"]["line"],
                    character=edit["range"]["start"]["character"],
                )
                end_pos = ls_types.Position(
                    line=edit["range"]["end"]["line"], character=edit["range"]["end"]["character"]
                )

                # Delete the old text and insert the new text
                self.delete_text_between_positions(relative_path, start_pos, end_pos)
                self.insert_text_at_position(
                    relative_path, start_pos["line"], start_pos["character"], edit["newText"]
                )
