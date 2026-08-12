from atlasleads.query_builder import build_search_queries, parse_comma_list, write_queries


def test_parse_comma_list_strips_and_drops_empty_items():
    assert parse_comma_list(" restaurante, padaria ,, açougue ") == [
        "restaurante",
        "padaria",
        "açougue",
    ]


def test_build_search_queries_combines_keywords_and_cities_with_uf():
    queries = build_search_queries(
        cities=["São Paulo", "Campinas"], keywords=["restaurante", "padaria"], uf="sp"
    )
    assert queries == [
        "restaurante em São Paulo - SP",
        "restaurante em Campinas - SP",
        "padaria em São Paulo - SP",
        "padaria em Campinas - SP",
    ]


def test_build_search_queries_without_uf_omits_suffix():
    queries = build_search_queries(cities=["São Paulo"], keywords=["restaurante"])
    assert queries == ["restaurante em São Paulo"]


def test_build_search_queries_skips_blank_entries():
    queries = build_search_queries(cities=["São Paulo", " "], keywords=["restaurante", ""])
    assert queries == ["restaurante em São Paulo"]


def test_write_queries_overwrite_deduplicates(tmp_path):
    output = tmp_path / "input.txt"
    added = write_queries(
        ["padaria em São Paulo - SP", "padaria em São Paulo - SP", "restaurante em Campinas - SP"],
        output_path=str(output),
        append=False,
    )
    assert added == 2
    assert output.read_text(encoding="utf-8").splitlines() == [
        "padaria em São Paulo - SP",
        "restaurante em Campinas - SP",
    ]


def test_write_queries_append_preserves_existing_and_skips_duplicates(tmp_path):
    output = tmp_path / "input.txt"
    output.write_text("padaria em São Paulo - SP\n", encoding="utf-8")

    added = write_queries(
        ["padaria em São Paulo - SP", "restaurante em Campinas - SP"],
        output_path=str(output),
        append=True,
    )

    assert added == 1
    assert output.read_text(encoding="utf-8").splitlines() == [
        "padaria em São Paulo - SP",
        "restaurante em Campinas - SP",
    ]
