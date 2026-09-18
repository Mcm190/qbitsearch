# VERSION: 1.0
# AUTHORS: Phuong Tran (phuongtm6994@gmail.com)
# CONTRIBUTORS: rewritten for qbitsearch to use only the Python standard
#               library (no BeautifulSoup) and to target nyaa.si instead of
#               the sukebei.nyaa.si adult-content mirror.

from html.parser import HTMLParser
from typing import Dict, List, Tuple, Union

from helpers import retrieve_url
from novaprinter import prettyPrinter


class nyaa:
    url = 'https://nyaa.si'
    name = 'Nyaa'
    # nyaa.si has no separate "movies"/"tv" split; both map to Live Action.
    supported_categories = {'all': '0_0',
                            'anime': '1_0',
                            'books': '5_0',
                            'games': '2_2',
                            'movies': '6_0',
                            'music': '3_0',
                            'software': '2_0',
                            'tv': '6_0'}

    class MyHtmlParser(HTMLParser):
        """ Sub-class for parsing results """
        def __init__(self, url: str) -> None:
            HTMLParser.__init__(self)
            self.url = url
            self.in_tbody = False
            self.in_row = False
            self.column = -1
            self.current_item: Dict[str, object] = {}
            self.page_items = 0

        def handle_starttag(self, tag: str, attrs: List[Tuple[str, Union[str, None]]]) -> None:
            params = dict(attrs)

            if tag == "tbody":
                self.in_tbody = True
                return

            if not self.in_tbody:
                return

            if tag == "tr":
                self.in_row = True
                self.column = -1
                self.current_item = {"link": "",
                                     "name": "",
                                     "size": "-1",
                                     "seeds": -1,
                                     "leech": -1,
                                     "engine_url": self.url,
                                     "desc_link": "",
                                     "pub_date": -1}
                return

            if not self.in_row:
                return

            if tag == "td":
                self.column += 1
                # the date column carries the timestamp as an attribute,
                # no need to parse the human-readable text
                timestamp = params.get("data-timestamp")
                if timestamp is not None:
                    self.current_item["pub_date"] = int(timestamp)
                return

            if tag == "a":
                href = params.get("href")
                if href is None:
                    return
                if self.column == 1 and href.startswith("/view/"):
                    self.current_item["name"] = params.get("title", "")
                    self.current_item["desc_link"] = self.url + href
                elif self.column == 2 and href.startswith("magnet:"):
                    self.current_item["link"] = href

        # nyaa.si always reports size as "<number> <unit>" (B/KiB/MiB/GiB/TiB)
        SIZE_UNITS = {"B": 1, "KIB": 1024, "MIB": 1024 ** 2, "GIB": 1024 ** 3, "TIB": 1024 ** 4}

        def handle_data(self, data: str) -> None:
            if not self.in_row:
                return
            data = data.strip()
            if self.column == 3 and data:
                try:
                    amount, unit = data.split()
                    self.current_item["size"] = str(int(float(amount) * self.SIZE_UNITS[unit.upper()]))
                except (ValueError, KeyError):
                    self.current_item["size"] = "-1"
            elif self.column == 5 and data.isdigit():
                self.current_item["seeds"] = int(data)
            elif self.column == 6 and data.isdigit():
                self.current_item["leech"] = int(data)

        def handle_endtag(self, tag: str) -> None:
            if tag == "tbody":
                self.in_tbody = False
            elif tag == "tr" and self.in_row:
                self.in_row = False
                if self.current_item.get("link"):
                    prettyPrinter(self.current_item)  # type: ignore[arg-type] # refactor later
                    self.page_items += 1

    def search(self, what: str, cat: str = 'all') -> None:
        """ Performs search """
        category = self.supported_categories[cat]

        for page in range(1, 5):
            parser = self.MyHtmlParser(self.url)
            page_url = f"{self.url}/?q={what}&f=0&c={category}&p={page}"
            html = retrieve_url(page_url)
            parser.feed(html)
            parser.close()
            if parser.page_items < 75:
                break
