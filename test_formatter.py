from formatter import clean_text, build_message, split_text, fingerprint


def test_social_removed_apply_kept():
    t = "Job at ACME\nApply: https://acme.com/jobs/1.\nJoin t.me/foo https://t.me/foo @foochannel\nhr@acme.com"
    out, links = clean_text(t)
    assert links == ["https://acme.com/jobs/1"]
    assert "t.me" not in out and "@foochannel" not in out
    assert "hr@acme.com" in out


def test_markdown_links():
    out, links = clean_text("[Apply here](https://forms.gle/x) and [our channel](https://t.me/abc)")
    assert links == ["https://forms.gle/x"]
    assert "t.me" not in out and "our channel" in out


def test_build_has_cta_and_link():
    m = build_message("Hiring accountant in Addis Ababa https://x.com/job1 https://acme.com/a", "CTA")
    assert m.endswith("CTA") and "https://acme.com/a" in m and "x.com/job1" not in m


def test_split():
    chunks = split_text(("a" * 100 + "\n\n") * 100, 1000)
    assert all(len(c) <= 1000 for c in chunks) and len(chunks) > 5


def test_fingerprint_ignores_source_noise():
    a = fingerprint("Senior Dev wanted!! https://acme.com/j @src1")
    b = fingerprint("senior dev wanted https://acme.com/j https://t.me/src2")
    assert a == b


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f()
            print("ok", n)
