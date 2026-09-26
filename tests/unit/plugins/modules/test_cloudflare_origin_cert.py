from fakes.cloudflare import FakeCloudflare, TOKEN

CSR = "-----BEGIN CERTIFICATE REQUEST-----\nMIIBfake\n-----END CERTIFICATE REQUEST-----\n"


def args(server, domain, csr=CSR):
    return dict(csr=csr, hostnames=[domain, "*." + domain], api_token=TOKEN, api_url=server.url)


def test_returns_the_certificate_cloudflare_holds(run, serve):
    cloudflare = FakeCloudflare()
    result = run("cloudflare_origin_cert", args(serve(cloudflare), "zertifikat.de"))
    assert result["certificate"] == cloudflare.certificates[result["certificate_id"]]["certificate"]


def test_covers_the_domain_and_its_wildcard(run, serve):
    cloudflare = FakeCloudflare()
    result = run("cloudflare_origin_cert", args(serve(cloudflare), "wildcard.de"))
    assert cloudflare.certificates[result["certificate_id"]]["hostnames"] == ["wildcard.de", "*.wildcard.de"]


def test_asks_for_fifteen_years(run, serve):
    server = serve(FakeCloudflare())
    run("cloudflare_origin_cert", args(server, "langlebig.de"))
    assert server.writes()[0].body["requested_validity"] == 5475


def test_sends_no_private_key(run, serve):
    server = serve(FakeCloudflare())
    run("cloudflare_origin_cert", args(server, "schluessel.de"))
    assert "PRIVATE KEY" not in str(server.writes()[0].body)


def test_check_mode_issues_nothing(run, serve):
    server = serve(FakeCloudflare())
    run("cloudflare_origin_cert", args(server, "probe.de"), check=True)
    assert server.requests == []


def test_refused_csr_fails_with_cloudflares_reason(run, serve):
    result = run("cloudflare_origin_cert", args(serve(FakeCloudflare()), "kaputt.de", csr="not a csr"))
    assert "Invalid CSR" in result["msg"]


def test_unreachable_cloudflare_fails(run, serve):
    server = serve(FakeCloudflare())
    server.outages = [504, 504, 504]
    assert run("cloudflare_origin_cert", args(server, "funkloch.de"))["failed"] is True


def test_certificate_that_reads_back_different_fails(run, serve):
    cloudflare = FakeCloudflare()
    cloudflare.certificates_drift = True
    assert "does not read back" in run("cloudflare_origin_cert", args(serve(cloudflare), "abweichung.de"))["msg"]


def test_issue_whose_answer_was_lost_is_not_repeated(run, serve):
    cloudflare = FakeCloudflare()
    server = serve(cloudflare)
    server.outages = ["lost"]
    run("cloudflare_origin_cert", args(server, "einzertifikat.de"))
    assert len(cloudflare.certificates) == 1


def test_certificate_read_back_as_null_fails_cleanly(run, serve):
    cloudflare = FakeCloudflare()
    cloudflare.certificates_drift = None
    assert "does not read back" in run("cloudflare_origin_cert", args(serve(cloudflare), "nullzert.de"))["msg"]
