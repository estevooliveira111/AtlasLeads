import pytest

from atlasleads import cli, ibge


def _municipality(id: int, nome: str, populacao: int) -> ibge.Municipality:
    return ibge.Municipality(
        id=id, nome=nome, uf_sigla="SP", uf_nome="São Paulo", populacao=populacao
    )


def _patch_cities(monkeypatch, cities: list[ibge.Municipality]) -> None:
    monkeypatch.setattr(
        ibge, "list_municipalities_with_population", lambda uf, use_cache=True: cities
    )


def test_normalize_argv_defaults_to_scrape_when_empty():
    assert cli._normalize_argv([]) == ["scrape"]


def test_normalize_argv_prepends_scrape_for_legacy_flags():
    assert cli._normalize_argv(["-s", "restaurante em SP", "-t", "5"]) == [
        "scrape", "-s", "restaurante em SP", "-t", "5",
    ]
    assert cli._normalize_argv(["--enrich-only"]) == ["scrape", "--enrich-only"]


def test_normalize_argv_leaves_known_subcommands_untouched():
    assert cli._normalize_argv(["locations", "states"]) == ["locations", "states"]
    assert cli._normalize_argv(["queries", "build", "--uf", "SP"]) == [
        "queries", "build", "--uf", "SP",
    ]


def test_scrape_subcommand_parses_legacy_style_flags():
    parser = cli._build_arg_parser()
    args = parser.parse_args(cli._normalize_argv(["-s", "padaria em São Paulo - SP", "-t", "10"]))
    assert args.command == "scrape"
    assert args.search == "padaria em São Paulo - SP"
    assert args.total == 10


def test_queries_build_dry_run_prints_generated_terms(monkeypatch, capsys):
    _patch_cities(
        monkeypatch,
        [_municipality(1, "São Paulo", 100), _municipality(2, "Campinas", 50)],
    )

    parser = cli._build_arg_parser()
    args = parser.parse_args(
        ["queries", "build", "--uf", "SP", "--keywords", "restaurante,padaria", "--dry-run"]
    )
    cli._run_queries(args)

    out = capsys.readouterr().out
    assert "restaurante em São Paulo - SP" in out
    assert "padaria em Campinas - SP" in out


def test_queries_build_min_population_filters_cities(monkeypatch, capsys):
    _patch_cities(
        monkeypatch,
        [_municipality(1, "São Paulo", 1_000_000), _municipality(2, "Vila Pequena", 500)],
    )

    parser = cli._build_arg_parser()
    args = parser.parse_args(
        [
            "queries", "build", "--uf", "SP", "--keywords", "restaurante",
            "--min-population", "10000", "--dry-run",
        ]
    )
    cli._run_queries(args)

    out = capsys.readouterr().out
    assert "São Paulo" in out
    assert "Vila Pequena" not in out


def test_queries_build_warns_on_unknown_city(monkeypatch, capsys):
    _patch_cities(monkeypatch, [_municipality(1, "São Paulo", 100)])

    parser = cli._build_arg_parser()
    args = parser.parse_args(
        [
            "queries", "build", "--uf", "SP", "--keywords", "restaurante",
            "--cities", "Cidade Que Nao Existe", "--dry-run",
        ]
    )
    with pytest.raises(SystemExit):
        cli._run_queries(args)

    out = capsys.readouterr().out
    assert "não encontrada" in out
