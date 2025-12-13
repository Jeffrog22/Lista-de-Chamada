# Gerenciador de Chamadas

Pequeno projeto com backend em FastAPI e interface desktop em CustomTkinter para registrar presenças a partir de uma planilha Excel (`chamadaBelaVista.xlsx`).

Como usar
- Instale dependências:

```bash
pip install -r requirements.txt
```

- Rodar o backend (na pasta do projeto):

```bash
uvicorn backend:app --reload
```

- Rodar a interface desktop:

```bash
python desktop_app.py
```

Principais endpoints
- `GET /api/filtros` — Retorna filtros (turmas, horários, professores, categorias, niveis)
- `GET /api/alunos` — Retorna alunos filtrados por turma/horário/professor/mês
- `POST /api/chamada` — Aceita payload em dois formatos para salvar presenças:
  - `{ "registros": { "Nome": { "dd/mm/YYYY": "c" } } }`
  - `{ "registros": [ { "Nome": "x", "Data": "dd/mm/YYYY", "Status": "c" }, ... ] }`

Observações
- O backend usa a planilha `chamadaBelaVista.xlsx` no mesmo diretório.
- Se o arquivo estiver aberto em outro programa, salvar pode falhar por permissão.
