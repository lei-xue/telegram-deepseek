import asyncio
import ipaddress
import json
import re
from html.parser import HTMLParser
from urllib.parse import urljoin

import httpx
from ddgs import DDGS

MAX_RESULTS = 5
PAGE_CHARS = 6000
MAX_BYTES = 2_000_000
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36"

SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web. Use it for current events, news, weather, prices, or facts you are unsure about.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Search query"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_url",
            "description": "Read the text of a web page, e.g. a search result that needs more detail.",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string", "description": "http(s) URL"}},
                "required": ["url"],
            },
        },
    },
]

PROMPT_HINT = (
    "You can use the web_search and open_url tools. You MUST search before answering questions about "
    "specific companies, products, AI models, software versions, people, prices, news, weather, or anything "
    "recent or that you are not certain about. Never answer such facts from memory or guess. If the search "
    "snippets are thin or conflicting, open the most relevant page with open_url. Answer from the results and "
    "mention the source briefly. Do not search for casual chat, feelings, or simple math."
)


def _args(arguments):
    try:
        return json.loads(arguments or "{}")
    except json.JSONDecodeError:
        return {}


def describe(name, arguments):
    args = _args(arguments)
    if name == "web_search":
        return f"🔎 Searching: {args.get('query', '')}"
    return f"📄 Reading: {args.get('url', '')}"


async def run(name, arguments):
    args = _args(arguments)
    try:
        if name == "web_search":
            return await asyncio.to_thread(_search, args["query"])
        if name == "open_url":
            return await _open(args["url"])
        return f"Unknown tool: {name}"
    except Exception as e:
        return f"Tool error: {e}"


def _search(query):
    results = DDGS(timeout=15).text(query, max_results=MAX_RESULTS)
    if not results:
        return "No results."
    return "\n\n".join(f"{i}. {r['title']}\n{r['href']}\n{r['body']}" for i, r in enumerate(results, 1))


async def _public_address(url):
    if url.scheme not in ("http", "https") or not url.host:
        raise ValueError("only http(s) URLs are allowed")
    infos = await asyncio.get_running_loop().getaddrinfo(url.raw_host.decode("ascii"), None)
    addresses = [ipaddress.ip_address(info[4][0].split("%")[0]) for info in infos]
    if not addresses or any(not address.is_global for address in addresses):
        raise ValueError("refusing to open a local or private address")
    return str(addresses[0])


async def _get(client, url):
    # Connect to the address that was checked, so a second DNS lookup cannot point elsewhere (DNS rebinding)
    url = httpx.URL(url)
    address = await _public_address(url)
    request = client.build_request("GET", url.copy_with(host=address), headers={"Host": url.netloc.decode("ascii")},
                                   extensions={"sni_hostname": url.raw_host.decode("ascii")})
    return await client.send(request, stream=True)


async def _read(response):
    # Stop reading after MAX_BYTES so a huge or endless body cannot exhaust memory
    body = bytearray()
    async for chunk in response.aiter_bytes():
        body += chunk
        if len(body) >= MAX_BYTES:
            break
    return bytes(body[:MAX_BYTES]).decode(response.encoding or "utf-8", errors="replace")


async def _open(url):
    async with httpx.AsyncClient(timeout=15, headers={"User-Agent": USER_AGENT}) as client:
        # Follow redirects by hand so every hop is checked against local addresses
        for _ in range(5):
            response = await _get(client, url)
            if not response.is_redirect:
                break
            await response.aclose()
            url = urljoin(url, response.headers["location"])
        else:
            raise ValueError("too many redirects")
        try:
            response.raise_for_status()
            body = await _read(response)
        finally:
            await response.aclose()
    if "html" in response.headers.get("content-type", ""):
        text = _html_to_text(body)
    else:
        text = body
    return text[:PAGE_CHARS] or "(empty page)"


class _TextExtractor(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "head", "nav", "footer", "form"}

    def __init__(self):
        super().__init__()
        self.parts, self.depth, self.title, self.in_title = [], 0, "", False

    def handle_starttag(self, tag, attrs):
        if tag == "body":
            self.depth = 0  # pages may omit </head>
        elif tag == "title":
            self.in_title = True
        elif tag in self.SKIP:
            self.depth += 1

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False
        elif tag in self.SKIP and self.depth:
            self.depth -= 1

    def handle_data(self, data):
        if self.in_title:
            self.title += data
        elif not self.depth:
            self.parts.append(data)


def _html_to_text(markup):
    parser = _TextExtractor()
    parser.feed(markup)
    text = "\n".join(line.strip() for line in "".join(parser.parts).splitlines())
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    title = parser.title.strip()
    return f"{title}\n\n{text}" if title else text
