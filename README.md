
# Gerador de Relatórios (Web – Flask) v2

Versão com:
- seleção de matéria (Português / Matemática)
- seleção dos dias da semana que o monitor trabalha
- atividades aleatórias por matéria
- interface de calibração visual (clicando na primeira página do PDF)

## Como rodar

1. Instale dependências:
```bash
pip install -r requirements.txt
```
2. Rode a aplicação:
```bash
python app.py
```
3. Acesse `http://localhost:8000`

## Calibração
Acesse `/calibrate`, envie o PDF e clique em 6 pontos (na ordem indicada). Isso atualiza `config.json` automaticamente.

## Notas técnicas
- A renderização da página do PDF usa PyMuPDF (fitz). Se houver erro de renderização, confirme que o PyMuPDF foi instalado corretamente.
- O arquivo `config.json` contém as coordenadas usadas para desenhar o overlay no PDF.
