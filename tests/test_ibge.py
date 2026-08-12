import pytest
import requests

from atlasleads import ibge

SUDESTE = {"id": 3, "sigla": "SE", "nome": "Sudeste"}

STATES_FIXTURE = [
    {"id": 35, "sigla": "SP", "nome": "São Paulo", "regiao": SUDESTE},
    {"id": 33, "sigla": "RJ", "nome": "Rio de Janeiro", "regiao": SUDESTE},
]

MUNICIPIOS_SP_FIXTURE = [
    {
        "id": 3550308,
        "nome": "São Paulo",
        "microrregiao": {
            "id": 35061,
            "nome": "São Paulo",
            "mesorregiao": {
                "id": 3515,
                "nome": "Metropolitana de São Paulo",
                "UF": {"id": 35, "sigla": "SP", "nome": "São Paulo", "regiao": {"nome": "Sudeste"}},
            },
        },
    },
    {
        "id": 3509502,
        "nome": "Campinas",
        "microrregiao": {
            "id": 35043,
            "nome": "Campinas",
            "mesorregiao": {
                "id": 3509,
                "nome": "Campinas",
                "UF": {"id": 35, "sigla": "SP", "nome": "São Paulo", "regiao": {"nome": "Sudeste"}},
            },
        },
    },
]

MUNICIPIOS_ONLY_NEW_HIERARCHY_FIXTURE = [
    {
        "id": 3509502,
        "nome": "Campinas",
        "regiao-imediata": {
            "id": 350045,
            "nome": "Campinas",
            "regiao-intermediaria": {
                "id": 3506,
                "nome": "Campinas",
                "UF": {"id": 35, "sigla": "SP", "nome": "São Paulo", "regiao": {"nome": "Sudeste"}},
            },
        },
    },
]

POPULACAO_SP_FIXTURE = [
    {
        "id": "9324",
        "variavel": "População residente estimada",
        "resultados": [
            {
                "series": [
                    {
                        "localidade": {"id": "3550308", "nome": "São Paulo - SP"},
                        "serie": {"2021": "12396372"},
                    },
                    {
                        "localidade": {"id": "3509502", "nome": "Campinas - SP"},
                        "serie": {"2021": "1223237"},
                    },
                    {
                        "localidade": {"id": "9999999", "nome": "Sem dado - SP"},
                        "serie": {"2021": "-"},
                    },
                ]
            }
        ],
    }
]


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


@pytest.fixture(autouse=True)
def isolate_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(ibge, "CACHE_DIR", str(tmp_path / "cache"))


def _fake_get_factory(routes: dict[str, object]):
    # Ordena por tamanho do fragmento (desc.) para que rotas mais específicas
    # (ex.: "/municipios") sejam checadas antes de rotas mais genéricas que
    # também aparecem como substring da mesma URL (ex.: "/estados").
    ordered_routes = sorted(routes.items(), key=lambda item: len(item[0]), reverse=True)

    def fake_get(url, params=None, timeout=None):
        for fragment, payload in ordered_routes:
            if fragment in url:
                return FakeResponse(payload)
        raise AssertionError(f"URL inesperada em teste: {url}")

    return fake_get


def test_list_states_parses_fields(monkeypatch):
    monkeypatch.setattr(
        requests, "get", _fake_get_factory({"/estados": STATES_FIXTURE})
    )
    states = ibge.list_states(use_cache=False)
    assert [s.sigla for s in states] == ["SP", "RJ"]
    assert states[0].nome == "São Paulo"
    assert states[0].regiao == "Sudeste"


def test_get_state_by_sigla_found_and_missing():
    states = [ibge.State(id=35, sigla="SP", nome="São Paulo", regiao="Sudeste")]
    assert ibge.get_state_by_sigla("sp", states).id == 35
    with pytest.raises(ValueError):
        ibge.get_state_by_sigla("XX", states)


def test_list_municipalities_sorted_and_parsed(monkeypatch):
    monkeypatch.setattr(
        requests, "get", _fake_get_factory({"/municipios": MUNICIPIOS_SP_FIXTURE})
    )
    cities = ibge.list_municipalities("sp", use_cache=False)
    assert [c.nome for c in cities] == ["Campinas", "São Paulo"]
    assert all(c.uf_sigla == "SP" for c in cities)
    assert cities[0].populacao is None


def test_list_municipalities_falls_back_to_new_region_hierarchy(monkeypatch):
    monkeypatch.setattr(
        requests,
        "get",
        _fake_get_factory({"/municipios": MUNICIPIOS_ONLY_NEW_HIERARCHY_FIXTURE}),
    )
    cities = ibge.list_municipalities("sp", use_cache=False)
    assert cities[0].nome == "Campinas"
    assert cities[0].uf_sigla == "SP"
    assert cities[0].uf_nome == "São Paulo"


def test_fetch_population_by_uf_parses_latest_value_and_skips_missing(monkeypatch):
    monkeypatch.setattr(
        requests,
        "get",
        _fake_get_factory({"/estados": STATES_FIXTURE, "/agregados": POPULACAO_SP_FIXTURE}),
    )
    population = ibge.fetch_population_by_uf("SP", use_cache=False)
    assert population[3550308] == 12396372
    assert population[3509502] == 1223237
    assert 9999999 not in population  # valor "-" (sem dado) deve ser ignorado


def test_list_municipalities_with_population_merges_data(monkeypatch):
    monkeypatch.setattr(
        requests,
        "get",
        _fake_get_factory(
            {
                "/estados": STATES_FIXTURE,
                "/municipios": MUNICIPIOS_SP_FIXTURE,
                "/agregados": POPULACAO_SP_FIXTURE,
            }
        ),
    )
    cities = ibge.list_municipalities_with_population("SP", use_cache=False)
    by_name = {c.nome: c for c in cities}
    assert by_name["São Paulo"].populacao == 12396372
    assert by_name["Campinas"].populacao == 1223237


def test_list_municipalities_with_population_degrades_gracefully_on_api_error(monkeypatch):
    def failing_get(url, params=None, timeout=None):
        if "/municipios" in url:
            return FakeResponse(MUNICIPIOS_SP_FIXTURE)
        raise requests.RequestException("boom")

    monkeypatch.setattr(requests, "get", failing_get)
    cities = ibge.list_municipalities_with_population("SP", use_cache=False)
    assert len(cities) == 2
    assert all(c.populacao is None for c in cities)


@pytest.mark.parametrize(
    "a, b",
    [
        ("São Paulo", "sao paulo"),
        ("  Ribeirão   Preto ", "ribeirao preto"),
        ("Não-Me-Toque", "nao-me-toque"),
    ],
)
def test_normalize_name_matches_accent_and_case_insensitive(a, b):
    assert ibge.normalize_name(a) == ibge.normalize_name(b)
