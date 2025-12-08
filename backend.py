import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timedelta
import calendar
from pydantic import BaseModel
from typing import List, Dict, Tuple
import time

# --- INICIALIZAÇÃO DO APP FASTAPI ---
app = FastAPI(
    title="API Gerenciador de Chamadas",
    description="Fornece dados da planilha de alunos e turmas.",
)

# --- CONFIGURAÇÃO DE CORS ---
# Permite que o frontend (rodando em outra porta/endereço) acesse esta API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Em produção, restrinja para o domínio do seu frontend
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- CONSTANTES E FUNÇÕES AUXILIARES ---
NOME_ARQUIVO = 'chamadaBelaVista.xlsx'
CACHE_EXPIRATION_SECONDS = 60  # Recarrega os dados do Excel a cada 60 segundos
_cache: Dict[str, any] = {"data": None, "timestamp": 0}

def get_dados_cached() -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Carrega os dados da planilha Excel, usando um cache em memória para evitar
    leituras repetidas do arquivo a cada requisição.
    """
    now = time.time()
    if now - _cache["timestamp"] > CACHE_EXPIRATION_SECONDS:
        try:
            xls = pd.ExcelFile(NOME_ARQUIVO)
            df_alunos = pd.read_excel(xls, sheet_name='Alunos').fillna("")
            df_turmas = pd.read_excel(xls, sheet_name='Turmas').fillna("")
            
            # Garante que a aba 'Registros' exista e tenha a coluna 'Nome'
            if 'Registros' in xls.sheet_names:
                df_registros = pd.read_excel(xls, sheet_name='Registros')
            else:
                df_registros = pd.DataFrame(columns=['Nome'])

            _cache["data"] = (df_alunos, df_turmas, df_registros)
            _cache["timestamp"] = now
        except FileNotFoundError:
            raise HTTPException(status_code=500, detail=f"Arquivo '{NOME_ARQUIVO}' não encontrado no servidor.")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Ocorreu um erro crítico ao ler a planilha: {e}")

    return _cache["data"]


def formatar_horario(horario):
    """Formata um objeto de tempo, string ou número para o formato 00h00."""
    if pd.isna(horario):
        return ""
    if isinstance(horario, (datetime, pd.Timestamp, pd.Timedelta)):
        return horario.strftime('%Hh%M')
    horario_str = str(horario).split('.')[0]
    try:
        return datetime.strptime(horario_str.zfill(4), '%H%M').strftime('%Hh%M')
    except ValueError:
        return horario_str

# --- MODELOS DE DADOS (PYDANTIC) ---
class ChamadaPayload(BaseModel):
    """Define a estrutura dos dados de chamada que o frontend enviará."""
    registros: Dict[str, Dict[str, str]]  # Ex: {"Nome Aluno": {"dd/mm/yyyy": "c"}}

# --- ENDPOINTS DA API ---

@app.get("/")
def root():
    """Endpoint raiz para verificar se a API está no ar."""
    return {"status": "API do Gerenciador de Chamadas está online"}

@app.get("/api/filtros")
def obter_opcoes_de_filtro():
    """Retorna listas de opções únicas para os filtros do frontend."""
    _, df_turmas, _ = get_dados_cached()
    
    turmas = df_turmas['Turma'].unique().tolist()
    
    # Formata os horários para exibição
    df_turmas['Horario_Formatado'] = df_turmas['Horário'].apply(formatar_horario)
    horarios = df_turmas['Horario_Formatado'].unique().tolist()
    
    professores = df_turmas['Professor'].unique().tolist()
    
    return {
        "turmas": turmas,
        "horarios": horarios,
        "professores": professores
    }

@app.get("/api/all-alunos")
def get_all_alunos():
    """Retorna a lista completa de alunos."""
    df_alunos, _, _ = get_dados_cached()
    return df_alunos.to_dict(orient='records')

@app.get("/api/all-turmas")
def get_all_turmas():
    """Retorna a lista completa de turmas."""
    _, df_turmas, _ = get_dados_cached()
    df_turmas['Horário'] = df_turmas['Horário'].apply(formatar_horario)
    return df_turmas.to_dict(orient='records')

@app.get("/api/alunos")
def obter_alunos_filtrados(
    turma: str = Query(...),
    horario: str = Query(...),
    professor: str = Query(...),
    mes: int = Query(...)
):
    """
    Retorna a lista de alunos e os registros de presença para um determinado mês.
    """
    df_alunos, _, df_registros = get_dados_cached()
    ano_vigente = datetime.now().year

    # --- Lógica para gerar as datas de aula (adaptada do Streamlit) ---
    dias_da_semana_validos = []
    nome_turma_lower = turma.lower()
    if "terça" in nome_turma_lower and "quinta" in nome_turma_lower:
        dias_da_semana_validos = [1, 3]  # Terça e Quinta
    elif "quarta" in nome_turma_lower and "sexta" in nome_turma_lower:
        dias_da_semana_validos = [2, 4]  # Quarta e Sexta
    else:
        dias_da_semana_validos = list(range(7)) # Padrão: todos os dias

    try:
        dias_no_mes = calendar.monthrange(ano_vigente, mes)[1]
        datas_mes_todas = [datetime(ano_vigente, mes, dia) for dia in range(1, dias_no_mes + 1)]
        datas_mes_filtradas = [data for data in datas_mes_todas if data.weekday() in dias_da_semana_validos]
        datas_mes_str = [data.strftime('%d/%m/%Y') for data in datas_mes_filtradas]
    except ValueError:
        raise HTTPException(status_code=400, detail="Mês inválido.")

    # Garante que as colunas de data existam no df_registros
    for data_str in datas_mes_str:
        if data_str not in df_registros.columns:
            df_registros[data_str] = ""

    # Preenche valores nulos com string vazia para evitar problemas com JSON
    df_registros = df_registros.fillna("")

    # Para garantir a correspondência, criamos uma coluna de horário formatado
    df_alunos['Horario_Formatado'] = df_alunos['Horário'].apply(formatar_horario)

    # Aplica os filtros
    alunos_filtrados = df_alunos[
        (df_alunos['Turma'] == turma) &
        (df_alunos['Horario_Formatado'] == horario) &
        (df_alunos['Professor'] == professor)
    ]

    # Junta os alunos filtrados com seus registros de presença
    alunos_com_registros = pd.merge(
        alunos_filtrados[['Turma', 'Horario_Formatado', 'Professor', 'Nível', 'Nome']],
        df_registros[['Nome'] + datas_mes_str],
        on='Nome',
        how='left'
    ).fillna("")

    # Renomeia a coluna de horário para o frontend
    alunos_com_registros = alunos_com_registros.rename(columns={"Horario_Formatado": "Horário"})

    return {
        "datas": datas_mes_str,
        "alunos": alunos_com_registros.to_dict(orient='records')
    }

@app.get("/api/relatorio/frequencia")
def obter_relatorio_frequencia(dias: int = 30):
    """Calcula e retorna as métricas de frequência para um período em dias."""
    try:
        _, _, df_registros = get_dados_cached()
    except Exception:
        return {"error": "Nenhum registro encontrado."}

    if df_registros.empty:
        return {"error": "Nenhum registro encontrado."}

    hoje = datetime.now()
    data_inicio = hoje - timedelta(days=dias) # Corrigido de datetime para timedelta
    colunas_identificacao = ['Nome', 'Turma', 'Horário', 'Professor', 'Nível']
    colunas_datas = [col for col in df_registros.columns if col not in colunas_identificacao]

    datas_relevantes = []
    for data_str in colunas_datas:
        try:
            data_col = datetime.strptime(data_str, '%d/%m/%Y')
            if data_inicio.date() <= data_col.date() <= hoje.date():
                datas_relevantes.append(data_str)
        except (ValueError, TypeError):
            continue

    if not datas_relevantes:
        return {"error": f"Nenhum registro de chamada nos últimos {dias} dias."}

    df_relatorio = df_registros[['Nome'] + datas_relevantes].copy().fillna('')
    df_relatorio.set_index('Nome', inplace=True)

    total_aulas = len(datas_relevantes)
    presencas = (df_relatorio == 'c').sum(axis=1)
    faltas = (df_relatorio == 'f').sum(axis=1)
    justificadas = (df_relatorio == 'j').sum(axis=1)
    aulas_consideradas = presencas + faltas
    frequencia_percentual = (presencas / aulas_consideradas.replace(0, 1)) * 100

    df_resultado = pd.DataFrame({
        'Total de Aulas no Período': total_aulas, 'Presenças (C)': presencas,
        'Faltas (F)': faltas, 'Faltas Justificadas (J)': justificadas,
        'Frequência (%)': frequencia_percentual.round(2)
    })
    return df_resultado.reset_index().to_dict(orient='records')

@app.post("/api/chamada")
def salvar_chamada(payload: ChamadaPayload):
    """Recebe e salva os registros de chamada na planilha."""
    try:
        # Carrega todos os dados do cache para uma reescrita segura
        df_alunos, df_turmas, df_registros_orig = get_dados_cached()
        df_registros = df_registros_orig.copy()

        for nome_aluno, registros_data in payload.registros.items():
            if nome_aluno not in df_registros['Nome'].values:
                nova_linha = pd.DataFrame([{'Nome': nome_aluno}])
                df_registros = pd.concat([df_registros, nova_linha], ignore_index=True)

            # Garante que o índice seja encontrado após uma possível concatenação
            idx_registro = df_registros[df_registros['Nome'] == nome_aluno].index

            for data, status in registros_data.items():
                if data not in df_registros.columns:
                    df_registros[data] = pd.NA
                df_registros.loc[idx_registro, data] = status if status else pd.NA

        # Reescreve o arquivo Excel inteiro com os dados atualizados.
        # Esta é a abordagem mais segura para garantir a integridade do arquivo.
        try:
            with pd.ExcelWriter(NOME_ARQUIVO, engine='openpyxl') as writer: # type: ignore
                df_alunos.to_excel(writer, sheet_name='Alunos', index=False)
                df_turmas.to_excel(writer, sheet_name='Turmas', index=False)
                df_registros.to_excel(writer, sheet_name='Registros', index=False)
        except PermissionError:
            raise HTTPException(status_code=500, detail=f"Erro de permissão. O arquivo '{NOME_ARQUIVO}' pode estar aberto em outro programa.")

        # Força a limpeza do cache para que a próxima leitura obtenha os dados salvos
        _cache["timestamp"] = 0

        return {"status": "Chamada salva com sucesso!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao salvar a chamada: {e}")

# Para rodar este servidor, use o comando no terminal:
# uvicorn backend:app --reload