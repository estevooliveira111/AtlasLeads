# AtlasLeads 📍

Um scraper de web leve e customizável desenvolvido com **Playwright** para extrair listagens de empresas do Google Maps. Ideal para coletar detalhes de contato, endereços, avaliações e muito mais.

**Nota:** Este projeto é apenas para **fins educacionais**. Sempre respeite os Termos de Serviço do Google e as políticas de scraping.

---

## 🚀 Funcionalidades

- Extração de nome, endereço, site, telefone e categoria.
- Coleta de métricas de avaliações (média e quantidade).
- Suporte a múltiplos termos de busca via arquivo `input.txt`.
- Exportação automática para **CSV** e **Excel (XLSX)**.
- Suporte a execução via **Docker**.
- Tratamento automático de diálogos de consentimento do Google.

---

## 📂 Exemplos de Saída

Os dados são salvos na pasta `GMaps Data`, organizada pela data de execução.

- **`nicho_em_local.csv`**
- **`nicho_em_local.xlsx`**

Cada entrada inclui:

- Nome da empresa
- Avaliação (média e total)
- Informações de contato (telefone, site)
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

3. **Instale as dependências:**
   ```bash
   pip install -r requirements.txt
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
   docker run -it --rm -v "$(pwd)/GMaps Data:/app/GMaps Data" atlasleads -s "Imobiliaria em Guarulhos" -t 50
   ```
   _O parâmetro `-v` garante que os arquivos gerados sejam salvos na sua máquina local._

---

## 📖 Como Usar

### Via Linha de Comando:

```bash
python3 main.py -s "Restaurantes em São Paulo" -t 50
```

- `-s`: Termo de busca.
- `-t`: Total de itens a serem extraídos (opcional).

### Via arquivo de entrada:

Adicione seus termos de busca no arquivo `input.txt` (um por linha) e execute:

```bash
python3 main.py -t 50
```

---

## ⚖️ Licença

Este projeto está sob a licença MIT. Veja o arquivo [LICENSE](LICENSE) para mais detalhes.
