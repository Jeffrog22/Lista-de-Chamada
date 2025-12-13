import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timedelta
import calendar
from pydantic import BaseModel
from typing import List, Dict, Tuple
import time, os

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

def calcular_idade(data_nascimento):
    """Calcula a idade a partir da data de nascimento."""
    if pd.isna(data_nascimento) or not isinstance(data_nascimento, (datetime, pd.Timestamp)):
        return None
    hoje = datetime.now()
    # Calcula a idade subtraindo o ano de nascimento do ano atual.
    # Em seguida, subtrai 1 se o aniversário deste ano ainda não ocorreu.
    idade = hoje.year - data_nascimento.year - ((hoje.month, hoje.day) < (data_nascimento.month, data_nascimento.day))
    return idade

def definir_categoria_por_idade(idade, df_categorias):
    """Define a categoria com base na idade, usando a tabela de categorias fornecida."""
    if pd.isna(idade) or idade is None:
        return "Não definida"
    
    # Itera sobre as regras de categoria carregadas da planilha
    for _, linha in df_categorias.iterrows():
        idade_min = linha.get('Idade Mínima', 0)
        idade_max = linha.get('Idade Máxima', float('inf'))
        if idade_min <= idade <= idade_max:
            return linha.get('Categoria', 'Não definida')
            
    return "Não definida"

def get_dados_cached() -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Carrega os dados da planilha Excel, usando um cache em memória para evitar
    leituras repetidas do arquivo a cada requisição.
    """
    now = time.time()
    # Verifica se o cache expirou ou se o arquivo foi modificado
    file_mod_time = os.path.getmtime(NOME_ARQUIVO) if os.path.exists(NOME_ARQUIVO) else 0
    if now - _cache.get("timestamp", 0) > CACHE_EXPIRATION_SECONDS or file_mod_time > _cache.get("timestamp", 0):
        try:
            xls = pd.ExcelFile(NOME_ARQUIVO)
            df_alunos = pd.read_excel(xls, sheet_name='Alunos').fillna("")
            df_turmas = pd.read_excel(xls, sheet_name='Turmas').fillna("")

            # Carrega categorias ou cria um DF vazio se a aba não existir
            if 'Categorias' in xls.sheet_names:
                df_categorias = pd.read_excel(xls, sheet_name='Categorias')
            else:
                df_categorias = pd.DataFrame(columns=['Categoria', 'Idade Mínima', 'Idade Máxima'])

            # --- CÁLCULO DE IDADE E CATEGORIA ---
            if 'Data de Nascimento' in df_alunos.columns:
                df_alunos['Data de Nascimento'] = pd.to_datetime(df_alunos['Data de Nascimento'], errors='coerce')
                df_alunos['Idade'] = df_alunos['Data de Nascimento'].apply(calcular_idade)
                df_alunos['Categoria'] = df_alunos['Idade'].apply(definir_categoria_por_idade, args=(df_categorias,))
                df_alunos['Idade'] = df_alunos['Idade'].fillna(0).astype(int)
            
            # Carrega registros ou cria um DF vazio se a aba não existir
            if 'Registros' in xls.sheet_names:
                df_registros = pd.read_excel(xls, sheet_name='Registros')
            else:
                df_registros = pd.DataFrame(columns=['Nome'])

            _cache["data"] = (df_alunos, df_turmas, df_registros, df_categorias)
            _cache["timestamp"] = now # Usa 'now' para o timestamp do cache
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
    df_alunos, df_turmas, _, df_categorias = get_dados_cached()
    
    turmas = df_turmas['Turma'].unique().tolist()
    
    # Formata os horários para exibição
    df_turmas['Horario_Formatado'] = df_turmas['Horário'].apply(formatar_horario)
    horarios = df_turmas['Horario_Formatado'].unique().tolist()
    
    professores = df_turmas['Professor'].unique().tolist()
    categorias = df_alunos['Categoria'].unique().tolist() if 'Categoria' in df_alunos.columns else []
    niveis = df_alunos['Nível'].unique().tolist() if 'Nível' in df_alunos.columns else []
    
    return {
        "turmas": turmas,
        "horarios": horarios,
        "professores": professores,
        "categorias": sorted([cat for cat in categorias if cat != "Não definida"]),
        "niveis": sorted([n for n in niveis if n != ""]) if niveis is not None else []
    }

@app.get("/api/all-alunos")
def get_all_alunos():
    """Retorna a lista completa de alunos."""
    df_alunos, _, _, _ = get_dados_cached()
    # Formata o horário para exibição consistente
    df_alunos['Horário'] = df_alunos['Horário'].apply(formatar_horario)
    return df_alunos.to_dict(orient='records')

@app.get("/api/all-turmas")
def get_all_turmas():
    """Retorna a lista completa de turmas."""
    df_alunos, df_turmas, _, _ = get_dados_cached()

    # Formata os horários em ambos os dataframes para garantir a correspondência
    df_alunos['Horario_Formatado'] = df_alunos['Horário'].apply(formatar_horario)
    df_turmas['Horario_Formatado'] = df_turmas['Horário'].apply(formatar_horario)

    # Calcula a contagem de alunos por turma/horário/professor
    student_counts = df_alunos.groupby(['Turma', 'Horario_Formatado', 'Professor']).size().reset_index(name='qtd.')

    # Junta a contagem de volta ao dataframe de turmas
    df_turmas_com_qtd = pd.merge(
        df_turmas,
        student_counts,
        on=['Turma', 'Horario_Formatado', 'Professor'],
        how='left'
    )
    
    # Preenche com 0 turmas que não têm alunos cadastrados e converte para inteiro
    df_turmas_com_qtd['qtd.'] = df_turmas_com_qtd['qtd.'].fillna(0).astype(int)

    # Usa o horário formatado para a resposta e remove colunas auxiliares
    df_turmas_com_qtd = df_turmas_com_qtd.rename(columns={"Horario_Formatado": "Horário"}).drop(columns=['Horário_x', 'Horário_y'], errors='ignore')
    return df_turmas_com_qtd.to_dict(orient='records')

@app.get("/api/categorias")
def get_all_categorias():
    """Retorna a lista completa de categorias com suas regras de idade."""
    _, _, _, df_categorias = get_dados_cached()
    return df_categorias.to_dict(orient='records')


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
    df_alunos, _, df_registros, _ = get_dados_cached()
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
        alunos_filtrados[['Turma', 'Horario_Formatado', 'Professor', 'Nível', 'Nome', 'Idade', 'Categoria']],
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
        _, _, df_registros, _ = get_dados_cached()
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
def salvar_chamada(payload: dict):
    """Recebe e salva os registros de chamada na planilha.

    Aceita dois formatos de payload:
    - Estrutura antiga/ideal: {"registros": {"Nome": {"dd/mm/yyyy": "c"}}}
    - Estrutura em lista: {"registros": [{"Nome": "x", "Data": "dd/mm/yyyy", "Status": "c"}, ...]}
    """
    try:
        # Carrega todos os dados do cache para uma reescrita segura
        df_alunos, df_turmas, df_registros_orig, df_categorias = get_dados_cached()
        df_registros = df_registros_orig.copy()

        registros = payload.get("registros")
        if registros is None:
            raise HTTPException(status_code=400, detail="Payload inválido: campo 'registros' ausente.")

        # Converte payload em formato de lista para o formato dict esperado
        if isinstance(registros, list):
            registros_dict: Dict[str, Dict[str, str]] = {}
            for rec in registros:
                nome = rec.get('Nome') or rec.get('name')
                data = rec.get('Data') or rec.get('data')
                status = rec.get('Status') or rec.get('status')
                if not nome or not data:
                    continue
                registros_dict.setdefault(nome, {})[data] = status
            registros = registros_dict

        if not isinstance(registros, dict):
            raise HTTPException(status_code=400, detail="Formato de 'registros' inválido.")

        for nome_aluno, registros_data in registros.items():
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
        try:
            with pd.ExcelWriter(NOME_ARQUIVO, engine='openpyxl') as writer: # type: ignore
                df_alunos.to_excel(writer, sheet_name='Alunos', index=False)
                df_turmas.to_excel(writer, sheet_name='Turmas', index=False)
                df_categorias.to_excel(writer, sheet_name='Categorias', index=False)
                df_registros.to_excel(writer, sheet_name='Registros', index=False)
        except PermissionError:
            raise HTTPException(status_code=500, detail=f"Erro de permissão. O arquivo '{NOME_ARQUIVO}' pode estar aberto em outro programa.")

        # Força a limpeza do cache para que a próxima leitura obtenha os dados salvos
        _cache["timestamp"] = 0

        return {"status": "Chamada salva com sucesso!"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao salvar a chamada: {e}")

# Para rodar este servidor, use o comando no terminal:
# uvicorn backend:app --reload