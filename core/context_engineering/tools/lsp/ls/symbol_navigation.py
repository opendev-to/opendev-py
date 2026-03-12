from __future__ import annotations

import logging
import os
import pathlib
from copy import copy
from pathlib import Path, PurePath
from typing import TYPE_CHECKING

from opendev.core.context_engineering.tools.lsp import ls_types
from opendev.core.context_engineering.tools.lsp.ls_exceptions import SolidLSPException
from opendev.core.context_engineering.tools.lsp.ls_utils import FileUtils
from opendev.core.context_engineering.tools.lsp.lsp_protocol_handler import lsp_types as LSPTypes

if TYPE_CHECKING:
    from opendev.core.context_engineering.tools.lsp.ls.server import (
        LSPFileBuffer,
        ReferenceInSymbol,
    )

log = logging.getLogger(__name__)


class SymbolNavigationMixin:
    """Mixin providing symbol body retrieval, referencing/containing/defining symbol methods."""

    def retrieve_symbol_body(
        self,
        symbol: ls_types.UnifiedSymbolInformation | LSPTypes.SymbolInformation,
        file_lines: list[str] | None = None,
        file_buffer: LSPFileBuffer | None = None,
    ) -> str:
        """
        Load the body of the given symbol. If the body is already contained in the symbol, just return it.
        """
        existing_body = symbol.get("body", None)
        if existing_body:
            return str(existing_body)

        assert "location" in symbol
        symbol_start_line = symbol["location"]["range"]["start"]["line"]
        symbol_end_line = symbol["location"]["range"]["end"]["line"]
        assert "relativePath" in symbol["location"]
        if file_lines is None:
            with self._open_file_context(symbol["location"]["relativePath"], file_buffer) as f:  # type: ignore
                file_lines = f.split_lines()
        symbol_body = "\n".join(file_lines[symbol_start_line : symbol_end_line + 1])

        # remove leading indentation
        symbol_start_column = symbol["location"]["range"]["start"]["character"]  # type: ignore
        symbol_body = symbol_body[symbol_start_column:]
        return symbol_body

    def request_referencing_symbols(
        self,
        relative_file_path: str,
        line: int,
        column: int,
        include_imports: bool = True,
        include_self: bool = False,
        include_body: bool = False,
        include_file_symbols: bool = False,
    ) -> list[ReferenceInSymbol]:
        """
        Finds all symbols that reference the symbol at the given location.
        This is similar to request_references but filters to only include symbols
        (functions, methods, classes, etc.) that reference the target symbol.

        :param relative_file_path: The relative path to the file.
        :param line: The 0-indexed line number.
        :param column: The 0-indexed column number.
        :param include_imports: whether to also include imports as references.
            Unfortunately, the LSP does not have an import type, so the references corresponding to imports
            will not be easily distinguishable from definitions.
        :param include_self: whether to include the references that is the "input symbol" itself.
            Only has an effect if the relative_file_path, line and column point to a symbol, for example a definition.
        :param include_body: whether to include the body of the symbols in the result.
        :param include_file_symbols: whether to include references that are file symbols. This
            is often a fallback mechanism for when the reference cannot be resolved to a symbol.
        :return: List of objects containing the symbol and the location of the reference.
        """
        from opendev.core.context_engineering.tools.lsp.ls.server import ReferenceInSymbol

        if not self.server_started:
            log.error("request_referencing_symbols called before Language Server started")
            raise SolidLSPException("Language Server not started")

        # First, get all references to the symbol
        references = self.request_references(relative_file_path, line, column)
        if not references:
            return []

        # For each reference, find the containing symbol
        result = []
        incoming_symbol = None
        for ref in references:
            ref_path = ref["relativePath"]
            assert ref_path is not None
            ref_line = ref["range"]["start"]["line"]
            ref_col = ref["range"]["start"]["character"]

            with self.open_file(ref_path) as file_data:
                # Get the containing symbol for this reference
                containing_symbol = self.request_containing_symbol(
                    ref_path, ref_line, ref_col, include_body=include_body
                )
                if containing_symbol is None:
                    # TODO: HORRIBLE HACK! I don't know how to do it better for now...
                    # THIS IS BOUND TO BREAK IN MANY CASES! IT IS ALSO SPECIFIC TO PYTHON!
                    # Background:
                    # When a variable is used to change something, like
                    #
                    # instance = MyClass()
                    # instance.status = "new status"
                    #
                    # we can't find the containing symbol for the reference to `status`
                    # since there is no container on the line of the reference
                    # The hack is to try to find a variable symbol in the containing module
                    # by using the text of the reference to find the variable name (In a very heuristic way)
                    # and then look for a symbol with that name and kind Variable
                    ref_text = file_data.contents.split("\n")[ref_line]
                    if "." in ref_text:
                        containing_symbol_name = ref_text.split(".")[0]
                        document_symbols = self.request_document_symbols(ref_path)
                        for symbol in document_symbols.iter_symbols():
                            if (
                                symbol["name"] == containing_symbol_name
                                and symbol["kind"] == ls_types.SymbolKind.Variable
                            ):
                                containing_symbol = copy(symbol)
                                containing_symbol["location"] = ref
                                containing_symbol["range"] = ref["range"]
                                break

                # We failed retrieving the symbol, falling back to creating a file symbol
                if containing_symbol is None and include_file_symbols:
                    log.warning(
                        f"Could not find containing symbol for {ref_path}:{ref_line}:{ref_col}. Returning file symbol instead"
                    )
                    fileRange = self._get_range_from_file_content(file_data.contents)
                    location = ls_types.Location(
                        uri=str(
                            pathlib.Path(os.path.join(self.repository_root_path, ref_path)).as_uri()
                        ),
                        range=fileRange,
                        absolutePath=str(os.path.join(self.repository_root_path, ref_path)),
                        relativePath=ref_path,
                    )
                    name = os.path.splitext(os.path.basename(ref_path))[0]

                    if include_body:
                        body = self.retrieve_full_file_content(ref_path)
                    else:
                        body = ""

                    containing_symbol = ls_types.UnifiedSymbolInformation(
                        kind=ls_types.SymbolKind.File,
                        range=fileRange,
                        selectionRange=fileRange,
                        location=location,
                        name=name,
                        children=[],
                        body=body,
                    )
                if containing_symbol is None or (
                    not include_file_symbols
                    and containing_symbol["kind"] == ls_types.SymbolKind.File
                ):
                    continue

                assert "location" in containing_symbol
                assert "selectionRange" in containing_symbol

                # Checking for self-reference
                if (
                    containing_symbol["location"]["relativePath"] == relative_file_path
                    and containing_symbol["selectionRange"]["start"]["line"] == ref_line
                    and containing_symbol["selectionRange"]["start"]["character"] == ref_col
                ):
                    incoming_symbol = containing_symbol
                    if include_self:
                        result.append(
                            ReferenceInSymbol(
                                symbol=containing_symbol, line=ref_line, character=ref_col
                            )
                        )
                        continue
                    log.debug(
                        f"Found self-reference for {incoming_symbol['name']}, skipping it since {include_self=}"
                    )
                    continue

                # checking whether reference is an import
                # This is neither really safe nor elegant, but if we don't do it,
                # there is no way to distinguish between definitions and imports as import is not a symbol-type
                # and we get the type referenced symbol resulting from imports...
                if (
                    not include_imports
                    and incoming_symbol is not None
                    and containing_symbol["name"] == incoming_symbol["name"]
                    and containing_symbol["kind"] == incoming_symbol["kind"]
                ):
                    log.debug(
                        f"Found import of referenced symbol {incoming_symbol['name']}"
                        f"in {containing_symbol['location']['relativePath']}, skipping"
                    )
                    continue

                result.append(
                    ReferenceInSymbol(symbol=containing_symbol, line=ref_line, character=ref_col)
                )

        return result

    def request_containing_symbol(
        self,
        relative_file_path: str,
        line: int,
        column: int | None = None,
        strict: bool = False,
        include_body: bool = False,
    ) -> ls_types.UnifiedSymbolInformation | None:
        """
        Finds the first symbol containing the position for the given file.
        For Python, container symbols are considered to be those with kinds corresponding to
        functions, methods, or classes (typically: Function (12), Method (6), Class (5)).

        The method operates as follows:
          - Request the document symbols for the file.
          - Filter symbols to those that start at or before the given line.
          - From these, first look for symbols whose range contains the (line, column).
          - If one or more symbols contain the position, return the one with the greatest starting position
            (i.e. the innermost container).
          - If none (strictly) contain the position, return the symbol with the greatest starting position
            among those above the given line.
          - If no container candidates are found, return None.

        :param relative_file_path: The relative path to the Python file.
        :param line: The 0-indexed line number.
        :param column: The 0-indexed column (also called character). If not passed, the lookup will be based
            only on the line.
        :param strict: If True, the position must be strictly within the range of the symbol.
            Setting to True is useful for example for finding the parent of a symbol, as with strict=False,
            and the line pointing to a symbol itself, the containing symbol will be the symbol itself
            (and not the parent).
        :param include_body: Whether to include the body of the symbol in the result.
        :return: The container symbol (if found) or None.
        """
        # checking if the line is empty, unfortunately ugly and duplicating code, but I don't want to refactor
        with self.open_file(relative_file_path):
            absolute_file_path = str(PurePath(self.repository_root_path, relative_file_path))
            content = FileUtils.read_file(absolute_file_path, self._encoding)
            if content.split("\n")[line].strip() == "":
                log.error(
                    f"Passing empty lines to request_container_symbol is currently not supported, {relative_file_path=}, {line=}"
                )
                return None

        document_symbols = self.request_document_symbols(relative_file_path)

        # make jedi and pyright api compatible
        # the former has no location, the later has no range
        # we will just always add location of the desired format to all symbols
        for symbol in document_symbols.iter_symbols():
            if "location" not in symbol:
                range = symbol["range"]
                location = ls_types.Location(
                    uri=f"file:/{absolute_file_path}",
                    range=range,
                    absolutePath=absolute_file_path,
                    relativePath=relative_file_path,
                )
                symbol["location"] = location
            else:
                location = symbol["location"]
                assert "range" in location
                location["absolutePath"] = absolute_file_path
                location["relativePath"] = relative_file_path
                location["uri"] = Path(absolute_file_path).as_uri()

        # Allowed container kinds, currently only for Python
        container_symbol_kinds = {
            ls_types.SymbolKind.Method,
            ls_types.SymbolKind.Function,
            ls_types.SymbolKind.Class,
        }

        def is_position_in_range(line: int, range_d: ls_types.Range) -> bool:
            start = range_d["start"]
            end = range_d["end"]

            column_condition = True
            if strict:
                line_condition = end["line"] >= line > start["line"]
                if column is not None and line == start["line"]:
                    column_condition = column > start["character"]
            else:
                line_condition = end["line"] >= line >= start["line"]
                if column is not None and line == start["line"]:
                    column_condition = column >= start["character"]
            return line_condition and column_condition

        # Only consider containers that are not one-liners (otherwise we may get imports)
        candidate_containers = [
            s
            for s in document_symbols.iter_symbols()
            if s["kind"] in container_symbol_kinds
            and s["location"]["range"]["start"]["line"] != s["location"]["range"]["end"]["line"]
        ]
        var_containers = [
            s for s in document_symbols.iter_symbols() if s["kind"] == ls_types.SymbolKind.Variable
        ]
        candidate_containers.extend(var_containers)

        if not candidate_containers:
            return None

        # From the candidates, find those whose range contains the given position.
        containing_symbols = []
        for symbol in candidate_containers:
            s_range = symbol["location"]["range"]
            if not is_position_in_range(line, s_range):
                continue
            containing_symbols.append(symbol)

        if containing_symbols:
            # Return the one with the greatest starting position (i.e. the innermost container).
            containing_symbol = max(
                containing_symbols, key=lambda s: s["location"]["range"]["start"]["line"]
            )
            if include_body:
                containing_symbol["body"] = self.retrieve_symbol_body(containing_symbol)
            return containing_symbol
        else:
            return None

    def request_container_of_symbol(
        self, symbol: ls_types.UnifiedSymbolInformation, include_body: bool = False
    ) -> ls_types.UnifiedSymbolInformation | None:
        """
        Finds the container of the given symbol if there is one. If the parent attribute is present, the parent is returned
        without further searching.

        :param symbol: The symbol to find the container of.
        :param include_body: whether to include the body of the symbol in the result.
        :return: The container of the given symbol or None if no container is found.
        """
        if "parent" in symbol:
            return symbol["parent"]
        assert "location" in symbol, f"Symbol {symbol} has no location and no parent attribute"
        return self.request_containing_symbol(
            symbol["location"]["relativePath"],  # type: ignore
            symbol["location"]["range"]["start"]["line"],
            symbol["location"]["range"]["start"]["character"],
            strict=True,
            include_body=include_body,
        )

    def request_defining_symbol(
        self,
        relative_file_path: str,
        line: int,
        column: int,
        include_body: bool = False,
    ) -> ls_types.UnifiedSymbolInformation | None:
        """
        Finds the symbol that defines the symbol at the given location.

        This method first finds the definition of the symbol at the given position,
        then retrieves the full symbol information for that definition.

        :param relative_file_path: The relative path to the file.
        :param line: The 0-indexed line number.
        :param column: The 0-indexed column number.
        :param include_body: whether to include the body of the symbol in the result.
        :return: The symbol information for the definition, or None if not found.
        """
        if not self.server_started:
            log.error("request_defining_symbol called before language server started")
            raise SolidLSPException("Language Server not started")

        # Get the definition location(s)
        definitions = self.request_definition(relative_file_path, line, column)
        if not definitions:
            return None

        # Use the first definition location
        definition = definitions[0]
        def_path = definition["relativePath"]
        assert def_path is not None
        def_line = definition["range"]["start"]["line"]
        def_col = definition["range"]["start"]["character"]

        # Find the symbol at or containing this location
        defining_symbol = self.request_containing_symbol(
            def_path, def_line, def_col, strict=False, include_body=include_body
        )

        return defining_symbol
