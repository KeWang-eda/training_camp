"""Terminal stream handler for real-time response display using rich text."""

from langchain.callbacks.base import BaseCallbackHandler
from rich.console import Console


class TerminalStreamHandler(BaseCallbackHandler):
    """Handles streaming of model responses to terminal with rich formatting."""

    def __init__(self, console: Console, initial_text: str = ""):
        """Initialize terminal stream handler.

        Args:
            console: Rich console for formatted output
            initial_text: Initial text to display
        """
        self.console = console
        self.full_response = initial_text
        self.in_code_block = False
        self.code_content = ""

    def on_llm_new_token(self, token: str, **kwargs) -> None:
        """Handle new token from LLM.

        Args:
            token: New token from the model
            **kwargs: Additional keyword arguments
        """
        self.full_response += token

        if "```" in token:
            parts = token.split("```")
            for index, part in enumerate(parts):
                if self.in_code_block:
                    self.code_content += part
                else:
                    if part:
                        self.console.print(part, end="", markup=False)

                if index < len(parts) - 1:
                    self._toggle_code_block()
            return

        if self.in_code_block:
            self.code_content += token
        else:
            self.console.print(token, end="", markup=False)

    def on_llm_end(self, response, **kwargs) -> None:
        """Handle end of LLM response.

        Args:
            response: Final response from the model
            **kwargs: Additional keyword arguments
        """
        # Print final newline if not already printed
        if self.full_response and not self.full_response.endswith("\n"):
            self.console.print()

    def on_llm_error(self, error: Exception, **kwargs) -> None:
        """Handle LLM errors.

        Args:
            error: Exception that occurred
            **kwargs: Additional keyword arguments
        """
        self.console.print(f"\n[bold red]Error:[/bold red] {str(error)}")

    def get_full_response(self) -> str:
        """Get the complete response text.

        Returns:
            Complete response text
        """
        return self.full_response

    def _toggle_code_block(self) -> None:
        """Toggle code block state and render buffered code when closing."""

        if not self.in_code_block:
            self.in_code_block = True
            self.code_content = ""
            return

        self.in_code_block = False
        if self.code_content.strip():
            self.console.print("\n[bold blue]Code:[/bold blue]")
            self.console.print(self.code_content, style="bold white on black")
        self.code_content = ""
