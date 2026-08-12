# AtlasLeads 📍

Um scraper de web leve e customizável desenvolvido com **Playwright** para extrair listagens de empresas do Google Maps. Ideal para coletar detalhes de contato, endereços, avaliações e muito mais.

**Nota:** Este projeto é apenas para **fins educacionais**. Sempre respeite os Termos de Serviço do Google e as políticas de scraping.

---

## 🚀 Funcionalidades

- Extração de nome, endereço, site, telefone e categoria.
- Coleta de métricas de avaliações (média e quantidade).
- Enriquecimento de contatos: visita o site de cada empresa e extrai e-mails e telefones extras.
- Suporte a múltiplos termos de busca via arquivo `input.txt`, com execução em paralelo (`-w`).
- Modo `--enrich-only` para reprocessar CSVs já coletados sem repetir a busca no Maps.
- Consulta de estados e municípios brasileiros (com população estimada) direto da **API do IBGE**.
- Geração automática de termos de busca combinando **cidades × palavras-chave** (ex.: `restaurante em Campinas - SP`), prontos para o `input.txt`.
- Exportação automática para **CSV** e **Excel (XLSX)**.
- Suporte a execução via **Docker**.
- Tratamento automático de diálogos de consentimento do Google.

---

## 📂 Estrutura do projeto

```
src/atlasleads/
├── cli.py             # parsing de argumentos e orquestração (scrape / locations / queries)
├── constants.py       # caminhos, limites, regexes e seletores do Maps
├── models.py           # Business / BusinessCollection (dedup + persistência CSV/XLSX)
├── enrichment.py       # scraping de e-mails/telefones no site de cada empresa
├── maps_scraper.py     # scraping do Google Maps via Playwright
├── ibge.py              # cliente da API do IBGE (estados, municípios, população)
└── query_builder.py     # combina cidades (IBGE) + palavras-chave em termos de busca
tests/                    # testes unitários (pytest) para a lógica pura do pacote
```

Cada busca roda em seu próprio processo (`ProcessPoolExecutor`), cada um com sua própria instância do Chromium. Dentro do enriquecimento de contatos de uma única empresa, sub-páginas candidatas são buscadas em paralelo com um `ThreadPoolExecutor`.

Os dados são salvos na pasta `output/`, organizada pela data de execução (`output/AAAA-MM-DD/`).

- **`nicho_em_local.csv`**
- **`nicho_em_local.xlsx`**

Cada entrada inclui:

- Nome da empresa
- Avaliação (média e total)
- Informações de contato (telefone, site, e-mails/telefones extraídos do site)
- Endereço e detalhes de localização
- Coordenadas (Latitude e Longitude)

---

## 🛠️ Instalação Local

1. **Clone o repositório:**

   ```bash
   git clone https://github.com/estevoo/AtlasLeads.git
   cd AtlasLeads
   ```

2. **Crie e ative um ambiente virtual:**

   ```bash
   python3 -m venv venv
   source venv/bin/activate  # No Windows: venv\Scripts\activate
   ```

3. **Instale o pacote e o navegador do Playwright:**
   ```bash
   pip install -e ".[dev]"
   playwright install chromium
   ```

---

## 🐳 Executando com Docker

Você pode rodar o scraper sem instalar nada localmente usando o Docker:

1. **Construir a imagem:**

   ```bash
   docker build -t atlasleads .
   ```

2. **Executar o scraper:**
   ```bash
   docker run -it --rm -v "$(pwd)/output:/app/output" atlasleads -s "Imobiliaria em Guarulhos" -t 50
   ```
   _O parâmetro `-v` garante que os arquivos gerados sejam salvos na sua máquina local._

---

## 📖 Como Usar

### Via Linha de Comando:

```bash
atlasleads -s "Restaurantes em São Paulo" -t 50
# equivalente a: python -m atlasleads -s "Restaurantes em São Paulo" -t 50
```

- `-s`: Termo de busca.
- `-t`: Total de itens a serem extraídos (opcional).
- `-w`: Número de buscas processadas em paralelo (opcional, padrão 1).

### Via arquivo de entrada:

Adicione seus termos de busca no arquivo `input.txt` (um por linha) e execute:

```bash
atlasleads -t 50 -w 3
```

### Reprocessar contatos de CSVs já coletados:

```bash
atlasleads --enrich-only
```

---

## 🌎 Dados do IBGE (estados, municípios, população)

O comando `locations` consulta a [API pública do IBGE](https://servicodados.ibge.gov.br/api/docs) para listar estados e municípios brasileiros, incluindo a população estimada mais recente de cada município. As respostas ficam em cache local (`output/.cache/`, por até 7 dias) para evitar consultas repetidas.

**Listar estados:**

```bash
atlasleads locations states
atlasleads locations states --json
```

**Listar municípios de uma UF, ordenados por população:**

```bash
atlasleads locations cities --uf SP --sort populacao --limit 20
atlasleads locations cities --uf SP --min-population 100000
```

---

## 🔀 Combinando cidades + palavras-chave

O comando `queries build` monta termos de busca combinando cidades (validadas contra a lista oficial do IBGE) com uma ou mais palavras-chave, no formato `<palavra-chave> em <Cidade> - <UF>` — pronto para ser usado com `atlasleads scrape -w N` a partir do `input.txt`.

**Escolher cidades específicas:**

```bash
atlasleads queries build --uf SP \
  --cities "São Paulo, Campinas, Santos" \
  --keywords "restaurante, padaria"
```

Isso grava em `input.txt`:

```
restaurante em São Paulo - SP
restaurante em Campinas - SP
restaurante em Santos - SP
padaria em São Paulo - SP
padaria em Campinas - SP
padaria em Santos - SP
```

**Usar todas as cidades de uma UF acima de uma população mínima** (sem `--cities`, todas as cidades da UF são usadas):

```bash
atlasleads queries build --uf SP --min-population 200000 --keywords "clínica odontológica"
```

**Outras opções úteis:**

- `--dry-run`: mostra os termos gerados sem gravar em disco.
- `--output arquivo.txt`: grava em outro arquivo em vez de `input.txt`.
- `--append`: preserva o conteúdo já existente no arquivo e só adiciona termos novos (por padrão, o arquivo é sobrescrito com a lista gerada).
- Cidades informadas em `--cities` que não forem encontradas na UF (nome digitado errado, ou abaixo do `--min-population`) geram um aviso no terminal e são ignoradas.

---

## ✅ Testes

```bash
pytest
```

Os testes cobrem a lógica pura do pacote: deduplicação de leads, extração de e-mails/telefones por regex, parsing de coordenadas, parsing das respostas da API do IBGE (com HTTP mockado) e a geração/gravação de termos de busca. O scraping via Playwright em si não é testado automaticamente, pois depende de navegação real no Google Maps.

---

## ⚖️ Licença

Este projeto está sob a licença MIT. Veja o arquivo [LICENSE](LICENSE) para mais detalhes.
