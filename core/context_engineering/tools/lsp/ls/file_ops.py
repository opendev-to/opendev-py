from __future__ import annotations

import logging
import pathlib
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import PurePath
from typing import TYPE_CHECKING

from opendev.core.context_engineering.tools.lsp import ls_types
from opendev.core.context_engineering.tools.lsp.ls_exceptions import SolidLSPException
from opendev.core.context_engineering.tools.lsp.ls_utils import FileUtils, TextUtils
from opendev.core.context_engineering.tools.lsp.lsp_protocol_handler.lsp_constants import (
    LSPConstants,
)
from opendev.core.context_engineering.tools.lsp.util.compat import MatchedConsecutiveLines

if TYPE_CHECKING:
    from opendev.core.context_engineering.tools.lsp.ls.server import LSPFileBuffer

log = logging.getLogger(__name__)


class FileOpsMixin:
    """Mixin providing file open/close, text insert/delete, and content retrieval methods."""

    @contextmanager
    def open_file(self, relative_file_path: str) -> Iterator[LSPFileBuffer]:
        """
        Open a file in the Language Server. This is required before making any requests to the Language Server.

        :param relative_file_path: The relative path of the file to open.
        """
        if not self.server_started:
            log.error("open_file called before Language Server started")
            raise SolidLSPException("Language Server not started")

        absolute_file_path = str(PurePath(self.repository_root_path, relative_file_path))
        uri = pathlib.Path(absolute_file_path).as_uri()

        if uri in self.open_file_buffers:
            assert self.open_file_buffers[uri].uri == uri
            assert self.open_file_buffers[uri].ref_count >= 1

            self.open_file_buffers[uri].ref_count += 1
            yield self.open_file_buffers[uri]
            self.open_file_buffers[uri].ref_count -= 1
        else:
            from opendev.core.context_engineering.tools.lsp.ls.server import LSPFileBuffer

            contents = FileUtils.read_file(absolute_file_path, self._encoding)

            version = 0
            self.open_file_buffers[uri] = LSPFileBuffer(uri, contents, version, self.language_id, 1)

            self.server.notify.did_open_text_document(
                {
                    LSPConstants.TEXT_DOCUMENT: {  # type: ignore
                        LSPConstants.URI: uri,
                        LSPConstants.LANGUAGE_ID: self.language_id,
                        LSPConstants.VERSION: 0,
                        LSPConstants.TEXT: contents,
                    }
                }
            )
            yield self.open_file_buffers[uri]
            self.open_file_buffers[uri].ref_count -= 1

        if self.open_file_buffers[uri].ref_count == 0:
            self.server.notify.did_close_text_document(
                {
                    LSPConstants.TEXT_DOCUMENT: {  # type: ignore
                        LSPConstants.URI: uri,
                    }
                }
            )
            del self.open_file_buffers[uri]

    @contextmanager
    def _open_file_context(
        self, relative_file_path: str, file_buffer: LSPFileBuffer | None = None
    ) -> Iterator[LSPFileBuffer]:
        """
        Internal context manager to open a file, optionally reusing an existing file buffer.

        :param relative_file_path: the relative path of the file to open.
        :param file_buffer: an optional existing file buffer to reuse.
        """
        if file_buffer is not None:
            yield file_buffer
        else:
            with self.open_file(relative_file_path) as fb:
                yield fb

    def insert_text_at_position(
        self, relative_file_path: str, line: int, column: int, text_to_be_inserted: str
    ) -> ls_types.Position:
        """
        Insert text at the given line and column in the given file and return
        the updated cursor position after inserting the text.

        :param relative_file_path: The relative path of the file to open.
        :param line: The line number at which text should be inserted.
        :param column: The column number at which text should be inserted.
        :param text_to_be_inserted: The text to insert.
        """
        if not self.server_started:
            log.error("insert_text_at_position called before Language Server started")
            raise SolidLSPException("Language Server not started")

        absolute_file_path = str(PurePath(self.repository_root_path, relative_file_path))
        uri = pathlib.Path(absolute_file_path).as_uri()

        # Ensure the file is open
        assert uri in self.open_file_buffers

        file_buffer = self.open_file_buffers[uri]
        file_buffer.version += 1

        new_contents, new_l, new_c = TextUtils.insert_text_at_position(
            file_buffer.contents, line, column, text_to_be_inserted
        )
        file_buffer.contents = new_contents
        self.server.notify.did_change_text_document(
            {
                LSPConstants.TEXT_DOCUMENT: {  # type: ignore
                    LSPConstants.VERSION: file_buffer.version,
                    LSPConstants.URI: file_buffer.uri,
                },
                LSPConstants.CONTENT_CHANGES: [
                    {
                        LSPConstants.RANGE: {
                            "start": {"line": line, "character": column},
                            "end": {"line": line, "character": column},
                        },
                        "text": text_to_be_inserted,
                    }
                ],
            }
        )
        return ls_types.Position(line=new_l, character=new_c)

    def delete_text_between_positions(
        self,
        relative_file_path: str,
        start: ls_types.Position,
        end: ls_types.Position,
    ) -> str:
        """
        Delete text between the given start and end positions in the given file and return the deleted text.
        """
        if not self.server_started:
            log.error("insert_text_at_position called before Language Server started")
            raise SolidLSPException("Language Server not started")

        absolute_file_path = str(PurePath(self.repository_root_path, relative_file_path))
        uri = pathlib.Path(absolute_file_path).as_uri()

        # Ensure the file is open
        assert uri in self.open_file_buffers

        file_buffer = self.open_file_buffers[uri]
        file_buffer.version += 1
        new_contents, deleted_text = TextUtils.delete_text_between_positions(
            file_buffer.contents,
            start_line=start["line"],
            start_col=start["character"],
            end_line=end["line"],
            end_col=end["character"],
        )
        file_buffer.contents = new_contents
        self.server.notify.did_change_text_document(
            {
                LSPConstants.TEXT_DOCUMENT: {  # type: ignore
                    LSPConstants.VERSION: file_buffer.version,
                    LSPConstants.URI: file_buffer.uri,
                },
                LSPConstants.CONTENT_CHANGES: [
                    {LSPConstants.RANGE: {"start": start, "end": end}, "text": ""}
                ],
            }
        )
        return deleted_text

    def retrieve_full_file_content(self, file_path: str) -> str:
        """
        Retrieve the full content of the given file.
        """
        import os

        if os.path.isabs(file_path):
            file_path = os.path.relpath(file_path, self.repository_root_path)
        with self.open_file(file_path) as file_data:
            return file_data.contents

    def retrieve_content_around_line(
        self,
        relative_file_path: str,
        line: int,
        context_lines_before: int = 0,
        context_lines_after: int = 0,
    ) -> MatchedConsecutiveLines:
        """
        Retrieve the content of the given file around the given line.

        :param relative_file_path: The relative path of the file to retrieve the content from
        :param line: The line number to retrieve the content around
        :param context_lines_before: The number of lines to retrieve before the given line
        :param context_lines_after: The number of lines to retrieve after the given line

        :return MatchedConsecutiveLines: A container with the desired lines.
        """
        with self.open_file(relative_file_path) as file_data:
            file_contents = file_data.contents
        return MatchedConsecutiveLines.from_file_contents(
            file_contents,
            line=line,
            context_lines_before=context_lines_before,
            context_lines_after=context_lines_after,
            source_file_path=relative_file_path,
        )
