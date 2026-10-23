import gzip

import pytest

from fakes.indexing import FakeSite, sitemapindex, urlset
from krot_index import web
from krot_index.sitemap import Sitemap


@pytest.fixture
def site():
    served = FakeSite()
    yield served
    served.close()


def test_pages_keep_the_sites_own_order(site):
    site.files["/sitemap.xml"] = urlset("https://rufnummer.de/", "https://rufnummer.de/vorwahl")
    assert list(Sitemap().pages(site.url("/sitemap.xml"))) == ["https://rufnummer.de/", "https://rufnummer.de/vorwahl"]


def test_index_is_opened_into_its_files(site):
    site.files["/sitemap.xml"] = sitemapindex(site.url("/sitemap-pages.xml"), site.url("/sitemap-profiles-1.xml"))
    site.files["/sitemap-pages.xml"] = urlset("https://abendseite.de/")
    site.files["/sitemap-profiles-1.xml"] = urlset("https://abendseite.de/profil/lena")
    assert list(Sitemap().pages(site.url("/sitemap.xml"))) == [
        "https://abendseite.de/", "https://abendseite.de/profil/lena"]


def test_card_is_named_by_its_sitemap_file(site):
    site.files["/sitemap.xml"] = sitemapindex(site.url("/sitemap-pages.xml"), site.url("/sitemap-profiles-1.xml"))
    site.files["/sitemap-pages.xml"] = urlset("https://abendseite.de/")
    site.files["/sitemap-profiles-1.xml"] = urlset("https://abendseite.de/profil/lena")
    pages = Sitemap().pages(site.url("/sitemap.xml"), cards_sitemap="sitemap-profiles")
    assert pages == {"https://abendseite.de/": False, "https://abendseite.de/profil/lena": True}


def test_card_is_named_by_its_path(site):
    site.files["/sitemap-5f1c.xml"] = urlset("https://rufnummer.de/vorwahl", "https://rufnummer.de/nummer/030123")
    pages = Sitemap().pages(site.url("/sitemap-5f1c.xml"), cards_path="^/nummer/")
    assert pages == {"https://rufnummer.de/vorwahl": False, "https://rufnummer.de/nummer/030123": True}


def test_closed_site_is_unreadable(site):
    site.files["/sitemap.xml"] = (401, "Authorization Required")
    assert Sitemap().pages(site.url("/sitemap.xml")) is None


def test_home_page_answered_for_any_path_is_unreadable(site):
    site.files["/sitemap.xml"] = (200, "<html><body>Willkommen</body></html>")
    assert Sitemap().pages(site.url("/sitemap.xml")) is None


def test_one_missing_file_makes_the_whole_site_unreadable(site):
    site.files["/sitemap.xml"] = sitemapindex(site.url("/sitemap-pages.xml"), site.url("/sitemap-gone.xml"))
    site.files["/sitemap-pages.xml"] = urlset("https://abendseite.de/")
    assert Sitemap().pages(site.url("/sitemap.xml")) is None


def test_redirect_is_not_followed(site):
    site.files["/sitemap.xml"] = (302, "")
    assert Sitemap().pages(site.url("/sitemap.xml")) is None


def test_empty_sitemap_is_an_empty_site_not_an_unreadable_one(site):
    site.files["/sitemap.xml"] = urlset()
    assert Sitemap().pages(site.url("/sitemap.xml")) == {}


def test_page_listed_twice_is_one_page(site):
    site.files["/sitemap.xml"] = urlset("https://rufnummer.de/", "https://rufnummer.de/")
    assert len(Sitemap().pages(site.url("/sitemap.xml"))) == 1


def test_dead_site_is_unreadable(site):
    address = site.url("/sitemap.xml")
    site.close()
    assert Sitemap().pages(address) is None


def test_gzipped_file_is_opened(site):
    site.files["/sitemap-1.xml.gz"] = gzip.compress(urlset("https://rufnummer.de/").encode())
    assert list(Sitemap().pages(site.url("/sitemap-1.xml.gz"))) == ["https://rufnummer.de/"]


def test_nested_file_on_another_host_is_not_fetched(site):
    site.files["/sitemap.xml"] = sitemapindex("http://169.254.169.254/latest/meta-data")
    assert Sitemap().pages(site.url("/sitemap.xml")) is None


def test_page_of_another_domain_makes_the_site_unreadable(site):
    site.files["/sitemap.xml"] = urlset("https://rufnummer.de/", "https://fremd.example/")
    assert Sitemap().pages(site.url("/sitemap.xml"), domain="rufnummer.de") is None


def test_pages_of_the_declared_domain_are_read(site):
    site.files["/sitemap.xml"] = urlset("https://Rufnummer.de/")
    assert list(Sitemap().pages(site.url("/sitemap.xml"), domain="rufnummer.de")) == ["https://Rufnummer.de/"]


def test_index_naming_a_local_file_is_unreadable(site):
    site.files["/sitemap.xml"] = sitemapindex("file:///etc/passwd")
    assert Sitemap().pages(site.url("/sitemap.xml")) is None


class CutOff:
    """web.call with the first `cuts` reads of addresses ending in `path` cut off, as a stalled read is."""

    def __init__(self, cuts, path=""):
        self.cuts = cuts
        self.path = path
        self.asked = []

    def __call__(self, method, url, **kwargs):
        self.asked.append(url)
        if self.cuts and url.endswith(self.path):
            self.cuts -= 1
            raise web.Unreachable("%s %s: timed out" % (method, web.shown(url)))
        return web.call(method, url, **kwargs)


def test_read_cut_off_once_is_asked_again(site):
    site.files["/sitemap.xml"] = urlset("https://abendseite.de/")
    assert list(Sitemap(CutOff(1)).pages(site.url("/sitemap.xml"))) == ["https://abendseite.de/"]


def test_nested_file_cut_off_once_is_asked_again(site):
    site.files["/sitemap.xml"] = sitemapindex(site.url("/sitemap-pages.xml"))
    site.files["/sitemap-pages.xml"] = urlset("https://abendseite.de/")
    assert list(Sitemap(CutOff(1, "/sitemap-pages.xml")).pages(site.url("/sitemap.xml"))) == ["https://abendseite.de/"]


def test_read_cut_off_twice_is_unreadable(site):
    site.files["/sitemap.xml"] = urlset("https://abendseite.de/")
    assert Sitemap(CutOff(2)).pages(site.url("/sitemap.xml")) is None


def test_read_cut_off_every_time_is_asked_only_twice(site):
    site.files["/sitemap.xml"] = urlset("https://abendseite.de/")
    fetch = CutOff(5)
    Sitemap(fetch).pages(site.url("/sitemap.xml"))
    assert len(fetch.asked) == 2


def test_read_cut_off_twice_says_so(site):
    site.files["/sitemap.xml"] = urlset("https://abendseite.de/")
    sitemap = Sitemap(CutOff(2))
    sitemap.pages(site.url("/sitemap.xml"))
    assert sitemap.failure == "GET %s: timed out (asked twice)" % site.url("/sitemap.xml")


# A status and a page that is no sitemap are the site's answer; asked again, it gives the same.
def test_refusal_is_not_asked_again(site):
    fetch = CutOff(0)
    Sitemap(fetch).pages(site.url("/sitemap.xml"))
    assert len(fetch.asked) == 1


def test_page_that_is_no_sitemap_is_not_asked_again(site):
    site.files["/sitemap.xml"] = (200, "<html><body>Willkommen</body></html>")
    fetch = CutOff(0)
    Sitemap(fetch).pages(site.url("/sitemap.xml"))
    assert len(fetch.asked) == 1


def test_answer_past_the_ceiling_is_not_asked_again(site):
    asked = []

    def oversized(method, url, **kwargs):
        asked.append(url)
        raise web.TooLarge("%s %s: answered more than %d bytes" % (method, url, web.MAX_BYTES))

    Sitemap(oversized).pages(site.url("/sitemap.xml"))
    assert len(asked) == 1


def test_failure_names_the_status(site):
    sitemap = Sitemap()
    sitemap.pages(site.url("/sitemap.xml"))
    assert sitemap.failure == "%s answered 404" % site.url("/sitemap.xml")


def test_failure_leaves_the_query_out(site):
    sitemap = Sitemap()
    sitemap.pages(site.url("/sitemap.xml?key=geheim42"))
    assert "geheim42" not in sitemap.failure


def test_readable_sitemap_clears_the_last_failure(site):
    site.files["/sitemap.xml"] = urlset("https://abendseite.de/")
    sitemap = Sitemap()
    sitemap.pages(site.url("/sitemap-gone.xml"))
    sitemap.pages(site.url("/sitemap.xml"))
    assert sitemap.failure is None
