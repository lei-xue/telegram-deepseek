import socket
import unittest
from unittest import mock

import httpx

from bot import tools

REAL_CLIENT = httpx.AsyncClient


def addrinfo(*ips):
    return [(socket.AF_INET6 if ":" in ip else socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0)) for ip in ips]


class OpenUrlTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.requests = []
        self.dns = {}

    async def fake_getaddrinfo(self, host, port, *args, **kwargs):
        answers = self.dns[host]
        # Each lookup returns the next answer, like a rebinding DNS server with TTL 0
        return addrinfo(answers.pop(0) if len(answers) > 1 else answers[0])

    async def open(self, url, handler):
        def handle(request):
            self.requests.append(request)
            return handler(request)

        def client(**kwargs):
            return REAL_CLIENT(transport=httpx.MockTransport(handle), **kwargs)

        loop = mock.Mock(getaddrinfo=self.fake_getaddrinfo)
        with mock.patch.object(tools.httpx, "AsyncClient", client), \
                mock.patch.object(tools.asyncio, "get_running_loop", return_value=loop):
            return await tools._open(url)

    async def test_connects_to_the_checked_address(self):
        self.dns["rebind.example"] = ["93.184.216.34", "127.0.0.1"]
        text = await self.open("https://rebind.example:8443/page?q=1", lambda r: httpx.Response(200, text="hello"))
        self.assertEqual(text, "hello")
        request = self.requests[0]
        self.assertEqual(request.url.host, "93.184.216.34")
        self.assertEqual(request.url.port, 8443)
        self.assertEqual(request.url.raw_path, b"/page?q=1")
        self.assertEqual(request.headers["Host"], "rebind.example:8443")
        self.assertEqual(request.extensions["sni_hostname"], "rebind.example")

    async def test_rejects_private_addresses(self):
        for host, ip in [("local.example", "127.0.0.1"), ("lan.example", "192.168.1.1"),
                         ("meta.example", "169.254.169.254"), ("v6.example", "::1")]:
            self.dns[host] = [ip]
            with self.assertRaises(ValueError):
                await self.open(f"http://{host}/", lambda r: httpx.Response(200, text="secret"))
        self.assertEqual(self.requests, [])

    async def test_rejects_other_schemes(self):
        with self.assertRaises(ValueError):
            await self.open("file:///etc/passwd", lambda r: httpx.Response(200))

    async def test_checks_every_redirect_hop(self):
        self.dns["public.example"] = ["93.184.216.34"]
        self.dns["internal.example"] = ["10.0.0.1"]
        with self.assertRaises(ValueError):
            await self.open("http://public.example/",
                            lambda r: httpx.Response(302, headers={"location": "http://internal.example/admin"}))
        self.assertEqual(len(self.requests), 1)

    async def test_follows_public_redirects(self):
        self.dns["a.example"] = ["93.184.216.34"]
        self.dns["b.example"] = ["93.184.216.35"]

        def handler(request):
            if request.headers["Host"] == "a.example":
                return httpx.Response(301, headers={"location": "http://b.example/next"})
            return httpx.Response(200, text="<html><title>B</title><body>done</body></html>",
                                  headers={"content-type": "text/html"})

        self.assertEqual(await self.open("http://a.example/", handler), "B\n\ndone")
        self.assertEqual(self.requests[1].url.host, "93.184.216.35")

    async def test_stops_reading_large_bodies(self):
        self.dns["big.example"] = ["93.184.216.34"]
        sent = 0

        async def endless():
            nonlocal sent
            while True:
                sent += 65536
                yield b"a" * 65536

        text = await self.open("http://big.example/", lambda r: httpx.Response(200, content=endless()))
        self.assertEqual(len(text), tools.PAGE_CHARS)
        self.assertLess(sent, tools.MAX_BYTES + 65536 * 2)


if __name__ == "__main__":
    unittest.main()
