"""Web Scraper module."""

import logging
from typing import Literal, TypedDict, final, override

import anyio
from pydantic import JsonValue

from .base_tool import BaseTool, RenderIn, RiskLevel, ToolCategory
from .web_search_engine import PageScraper

logger = logging.getLogger(__name__)


class WebScraperParametersSchema(TypedDict):
    type: Literal["object"]
    properties: dict[str, JsonValue]
    required: list[str]


@final
class WebScraperTool(BaseTool):
    """외부 웹사이트 또는 문서를 크롤링하여 Markdown 형식으로 반환하는 도구입니다."""

    category: ToolCategory = ToolCategory.SEARCH
    render_in: RenderIn = RenderIn.CONTEXTUAL
    risk_level: RiskLevel = RiskLevel.SAFE
    icon: str = "🕸️"
    tags: list[str] = ["crawl", "scrape", "documentation", "web"]

    _name: str
    _description: str
    _schema: WebScraperParametersSchema

    def __init__(self) -> None:
        """Initialize the WebScraperTool."""
        super().__init__()
        self._name = "web_scrape"
        self._description = (
            "Fetches a web page by URL and extracts its main content as Markdown. "
            "Useful for reading external documentation or articles."
        )
        self._schema = {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "The full URL of the web page to scrape."},
            },
            "required": ["url"],
        }

    @property
    @override
    def name(self) -> str:
        """Name.

        Returns:
            str: The str result.

        """
        return self._name

    @property
    @override
    def description(self) -> str:
        """Description.

        Returns:
            str: The str result.

        """
        return self._description

    @property
    @override
    def parameters_schema(self) -> WebScraperParametersSchema:
        """Parameters Schema.

        Returns:
            dict[str, Any]: The dict[str, any] result.

        """
        return self._schema

    @override
    def execute(self, **kwargs: object) -> str:
        """Execute.

        Args:
            **kwargs: kwargs.

        Returns:
            Any: The any result.

        """
        url_value = kwargs.get("url")
        url = url_value if isinstance(url_value, str) else ""
        if not url:
            return "Error: 'url' parameter is required."

        try:
            logger.info("Scraping URL: %s", url)

            async def fetch() -> str:
                scraper = PageScraper()
                try:
                    return await scraper.extract_text(url, max_chars=10000)
                finally:
                    await scraper.close()

            text = anyio.run(fetch)
            return f"Source: {url}\n\n{text}"
        except (OSError, RuntimeError, ValueError) as e:
            return f"Error fetching URL: {str(e)}"
        except Exception as e:
            logger.exception("Unhandled exception")
            return f"Error processing content: {str(e)}"
