import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox
from tkinter import font as tkfont
import requests
import threading
from datetime import datetime

# --- CONFIGURAÇÕES GLOBAIS ---
API_BASE_URL = "http://127.0.0.1:8000"

# Mapeamento de status (similar ao do Streamlit)
STATUS_MAP = {
    0: {"text": " ", "code": "", "fg_color": ("#f0f2f6", "#343638"), "hover_color": ("#e0e2e4", "#4a4d50")},
    1: {"text": "✅", "code": "c", "fg_color": "#2ECC71", "hover_color": "#25a25a"}, # Presente
    2: {"text": "❌", "code": "f", "fg_color": "#E74C3C", "hover_color": "#c0392b"}, # Ausente
    3: {"text": "●", "code": "j", "fg_color": "#F39C12", "hover_color": "#d35400"}, # Justificado (Círculo)
}

class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Gerenciador de Chamadas")
        self.geometry("1200x700")
        ctk.set_appearance_mode("System")

        # --- ESTRUTURA PRINCIPAL ---
        # Coluna 0: Sidebar (pode ser escondida), Coluna 1: Conteúdo Principal
        self.grid_columnconfigure(1, weight=1)
        # Linha 0: Espaço para o botão de menu, Linha 1: Conteúdo principal e sidebar
        self.grid_rowconfigure(1, weight=1)

        # --- BOTÃO DE MENU RETRÁTIL (CANTO SUPERIOR ESQUERDO) ---
        self.menu_button = ctk.CTkButton(self, text="☰", width=40, font=ctk.CTkFont(size=20), command=self.toggle_sidebar)
        self.menu_button.grid(row=0, column=0, padx=10, pady=10, sticky="nw")
 
        # --- 1. SIDEBAR (PAINEL LATERAL) ---
        self.sidebar_frame = ctk.CTkFrame(self, width=250, corner_radius=0)
        self.sidebar_frame.grid(row=1, column=0, sticky="nsew") # Movido para a linha 1
        self.sidebar_frame.grid_rowconfigure(5, weight=1) # Espaço para empurrar o botão de salvar para baixo

        # --- 1.1. Frame do Menu Principal (visível no início) ---
        self.main_menu_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        self.main_menu_frame.grid(row=0, column=0, sticky="nsew")
        self.main_menu_label = ctk.CTkLabel(self.main_menu_frame, text="Menu Principal", font=ctk.CTkFont(size=20, weight="bold"))
        self.main_menu_label.grid(row=0, column=0, padx=20, pady=(20, 10))
        
        # Cria os botões do menu principal dinamicamente
        menu_items = ["Chamada", "Alunos", "Turmas"]
        for i, item in enumerate(menu_items, start=1):
            button = ctk.CTkButton(self.main_menu_frame, text=item, command=lambda v=item: self.show_view(v))
            button.grid(row=i, column=0, padx=20, pady=10, sticky="ew")
            
        # --- 1.2. Frame do Menu de Controle da CHAMADA (inicialmente oculto) ---
        self.chamada_control_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        # (grid é chamado em show_view)
        self.chamada_control_label = ctk.CTkLabel(self.chamada_control_frame, text="Controle de Chamada", font=ctk.CTkFont(size=16, weight="bold"))
        self.chamada_control_label.grid(row=0, column=0, columnspan=2, padx=20, pady=(20, 10))
        self.chamada_turma_combo = ctk.CTkComboBox(self.chamada_control_frame, values=["Carregando..."])
        self.chamada_turma_combo.grid(row=1, column=0, columnspan=2, padx=20, pady=10, sticky="ew")
        self.chamada_horario_combo = ctk.CTkComboBox(self.chamada_control_frame, values=["Carregando..."])
        self.chamada_horario_combo.grid(row=2, column=0, columnspan=2, padx=20, pady=10, sticky="ew")
        
        self.chamada_prof_label = ctk.CTkLabel(self.chamada_control_frame, text="Professor(a):")
        self.chamada_prof_label.grid(row=3, column=0, columnspan=2, padx=20, pady=(10,0), sticky="w")
        self.chamada_prof_var = tk.StringVar()
        self.chamada_prof_frame = ctk.CTkFrame(self.chamada_control_frame, fg_color="transparent") # Frame para os radio buttons
        self.chamada_prof_frame.grid(row=4, column=0, columnspan=2, padx=20, pady=5, sticky="ew")

        self.chamada_buscar_button = ctk.CTkButton(self.chamada_control_frame, text="Buscar Alunos", command=self.iniciar_busca_alunos)
        self.chamada_buscar_button.grid(row=5, column=0, columnspan=2, padx=20, pady=10, sticky="ew")
        self.chamada_back_button = ctk.CTkButton(self.chamada_control_frame, text="< Voltar ao Menu", command=self.show_main_menu, fg_color="transparent", border_width=1)
        self.chamada_back_button.grid(row=7, column=0, columnspan=2, padx=20, pady=(20, 10), sticky="s")

        # --- 1.3. Frame do Menu de Controle de ALUNOS (inicialmente oculto) ---
        self.alunos_control_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        # (grid é chamado em show_view)
        self.alunos_control_label = ctk.CTkLabel(self.alunos_control_frame, text="Filtros de Alunos", font=ctk.CTkFont(size=16, weight="bold"))
        self.alunos_control_label.grid(row=0, column=0, columnspan=2, padx=20, pady=(20, 10))

        self.alunos_turma_combo = ctk.CTkComboBox(self.alunos_control_frame, values=["Carregando..."])
        self.alunos_turma_combo.grid(row=1, column=0, columnspan=2, padx=20, pady=10, sticky="ew")
        self.alunos_horario_combo = ctk.CTkComboBox(self.alunos_control_frame, values=["Carregando..."])
        self.alunos_horario_combo.grid(row=2, column=0, columnspan=2, padx=20, pady=10, sticky="ew")

        self.alunos_prof_label = ctk.CTkLabel(self.alunos_control_frame, text="Professor(a):")
        self.alunos_prof_label.grid(row=3, column=0, columnspan=2, padx=20, pady=(10,0), sticky="w")
        self.alunos_prof_var = tk.StringVar()
        self.alunos_prof_frame = ctk.CTkFrame(self.alunos_control_frame, fg_color="transparent") # Frame para os radio buttons
        self.alunos_prof_frame.grid(row=4, column=0, columnspan=2, padx=20, pady=5, sticky="ew")


        self.alunos_nivel_label = ctk.CTkLabel(self.alunos_control_frame, text="Nível:")
        self.alunos_nivel_label.grid(row=5, column=0, columnspan=2, padx=20, pady=(10,0), sticky="w")
        self.alunos_nivel_combo = ctk.CTkComboBox(self.alunos_control_frame, values=["Todos"])
        self.alunos_nivel_combo.grid(row=6, column=0, columnspan=2, padx=20, pady=10, sticky="ew")

        self.alunos_categoria_label = ctk.CTkLabel(self.alunos_control_frame, text="Categoria:")
        self.alunos_categoria_label.grid(row=9, column=0, columnspan=2, padx=20, pady=(10,0), sticky="w")
        self.alunos_categoria_combo = ctk.CTkComboBox(self.alunos_control_frame, values=["Todas"])
        self.alunos_categoria_combo.grid(row=10, column=0, columnspan=2, padx=20, pady=10, sticky="ew")

        self.alunos_buscar_button = ctk.CTkButton(self.alunos_control_frame, text="Filtrar", command=self.aplicar_filtros_alunos)
        self.alunos_buscar_button.grid(row=11, column=0, columnspan=2, padx=20, pady=10, sticky="ew")

        self.alunos_limpar_button = ctk.CTkButton(self.alunos_control_frame, text="Limpar Filtros", command=self.limpar_filtros_alunos, fg_color="transparent", border_width=1)
        self.alunos_limpar_button.grid(row=12, column=0, columnspan=2, padx=20, pady=(0, 10), sticky="ew")

        self.alunos_back_button = ctk.CTkButton(self.alunos_control_frame, text="< Voltar ao Menu", command=self.show_main_menu, fg_color="transparent", border_width=1)
        self.alunos_back_button.grid(row=13, column=0, columnspan=2, padx=20, pady=(20, 10), sticky="s")

        # --- 2. ÁREA PRINCIPAL (MAIN CONTENT) ---
        self.main_content_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.main_content_frame.grid(row=0, column=1, rowspan=2, sticky="nsew", padx=0, pady=0) # Ocupa as linhas 0 e 1
        self.main_content_frame.grid_rowconfigure(0, weight=1)
        self.main_content_frame.grid_columnconfigure(0, weight=1)

        # --- 2.1. Área com Abas ---
        self.tab_view = ctk.CTkTabview(self.main_content_frame, corner_radius=8)
        self.tab_view.grid(row=0, column=0, padx=20, pady=(10, 20), sticky="nsew")
        self.tab_view.add("Chamada")
        self.tab_view.add("Alunos")
        self.tab_view.add("Turmas")
        self.tab_view.set("Chamada") 

        # --- 2.2. Conteúdo da Aba "Chamada" ---
        self.tab_view.tab("Chamada").grid_columnconfigure(0, weight=1)
        self.tab_view.tab("Chamada").grid_columnconfigure(1, weight=0) # Coluna para o botão
        self.tab_view.tab("Chamada").grid_rowconfigure(1, weight=1)
        self.chamada_info_label = ctk.CTkLabel(self.tab_view.tab("Chamada"), text="Use o menu de controle para buscar uma turma.", font=ctk.CTkFont(size=14))
        self.chamada_info_label.grid(row=0, column=0, padx=10, pady=10, sticky="w")
        self.chamada_salvar_button = ctk.CTkButton(self.tab_view.tab("Chamada"), text="Salvar Alterações", command=self.iniciar_salvar_chamada, fg_color="#007bff", hover_color="#0056b3")
        self.chamada_salvar_button.grid(row=0, column=1, padx=10, pady=10, sticky="e")
        self.chamada_scroll_frame = ctk.CTkScrollableFrame(self.tab_view.tab("Chamada"), label_text="Lista de Chamada")
        self.chamada_scroll_frame.grid(row=1, column=0, columnspan=2, sticky="nsew")

        # --- 2.3. Conteúdo da Aba "Alunos" ---
        self.tab_view.tab("Alunos").grid_columnconfigure(0, weight=1)
        self.tab_view.tab("Alunos").grid_rowconfigure(0, weight=1)
        self.alunos_scroll_frame = ctk.CTkScrollableFrame(self.tab_view.tab("Alunos"), label_text="Cadastro Geral de Alunos")
        self.alunos_scroll_frame.grid(row=0, column=0, sticky="nsew")

        # --- 2.4. Conteúdo da Aba "Turmas" ---
        self.tab_view.tab("Turmas").grid_columnconfigure(0, weight=1)
        self.tab_view.tab("Turmas").grid_rowconfigure(0, weight=1)
        self.turmas_scroll_frame = ctk.CTkScrollableFrame(self.tab_view.tab("Turmas"), label_text="Lista de Turmas e Atalhos")
        self.turmas_scroll_frame.grid(row=0, column=0, sticky="nsew")

        # --- ARMAZENAMENTO DE ESTADO ---
        self.sidebar_is_open = True
        meses = [datetime(2000, i, 1).strftime('%B') for i in range(1, 13)]
        self.mes_atual_str = meses[datetime.now().month - 1]
        self.chamada_data = {} # Guarda os dados da API
        self.chamada_widgets = {} # Guarda os widgets de botão para poder ler o estado
        self.all_students_data = None # Cache para todos os alunos
        self.categorias_data = None # Cache para as categorias
        
        # Mapeamento de views para seus frames de controle
        self.control_frames = {
            "Chamada": self.chamada_control_frame,
            "Alunos": self.alunos_control_frame,
        }

        # --- INICIALIZAÇÃO ---
        self.carregar_filtros_iniciais()
        self.show_main_menu() # Garante que o menu principal seja exibido no início

    def toggle_sidebar(self):
        """Mostra ou esconde o painel lateral."""
        if self.sidebar_is_open:
            self.sidebar_frame.grid_forget()
            self.sidebar_is_open = not self.sidebar_is_open
        else:
            # Garante que ao reabrir, sempre mostre o menu principal
            self.show_main_menu()
            self.sidebar_frame.grid(row=1, column=0, sticky="nsew")
            self.sidebar_is_open = not self.sidebar_is_open

    def show_view(self, view_name: str):
        """Muda a aba principal e ajusta a sidebar."""
        self.tab_view.set(view_name)

        # Esconde todos os paineis de controle e o menu principal
        for frame in self.control_frames.values():
            frame.grid_forget()
        self.main_menu_frame.grid_forget()

        if view_name in self.control_frames:
            self.control_frames[view_name].grid(row=0, column=0, sticky="nsew")
        if view_name == "Alunos":
            self.iniciar_busca_todos_alunos() # Carrega todos os alunos ao entrar na aba
        elif view_name == "Turmas": # A view de Turmas não precisa de menu de controle
            self.carregar_lista_turmas() # Carrega a lista ao entrar na aba
            # Recolhe o menu ao selecionar "Turmas"
            if self.sidebar_is_open:
                self.toggle_sidebar()

    def show_main_menu(self):
        """Mostra o menu principal e esconde os de controle."""
        for frame in self.control_frames.values():
            frame.grid_forget()
        self.main_menu_frame.grid(row=0, column=0, sticky="nsew")

    def run_in_thread(self, target_func):
        """Executa uma função em uma nova thread para não travar a UI."""
        thread = threading.Thread(target=target_func)
        thread.daemon = True
        thread.start()

    def carregar_filtros_iniciais(self):
        def _task():
            try:
                response = requests.get(f"{API_BASE_URL}/api/filtros")
                response.raise_for_status()
                data = response.json() # Processa os dados na thread

                def _update_ui(): # Função para atualizar a UI na thread principal
                    turmas = data.get('turmas', []) or []
                    horarios = data.get('horarios', []) or []
                    self.chamada_turma_combo.configure(values=turmas)
                    self.chamada_turma_combo.set(turmas[0] if turmas else "")
                    self.chamada_horario_combo.configure(values=horarios)
                    self.chamada_horario_combo.set(horarios[0] if horarios else "")
                    professores = data.get('professores', [])
                    self._criar_radio_professores(professores)
                    # Remove a opção "Todos" e define um valor padrão vazio
                    self.alunos_turma_combo.configure(values=data.get('turmas', []))
                    self.alunos_turma_combo.set("")
                    self.alunos_horario_combo.configure(values=data.get('horarios', []))
                    self.alunos_horario_combo.set("")
                    niveis = data.get('niveis', [])
                    self.alunos_nivel_combo.configure(values=niveis)
                    self.alunos_nivel_combo.set("")
                    self.carregar_categorias() # Inicia o carregamento das categorias
                self.after(0, _update_ui) # Agenda a atualização da UI

            except requests.exceptions.RequestException as e:
                self.after(0, lambda: messagebox.showerror("Erro de Conexão", f"Não foi possível carregar os filtros da API.\nVerifique se o backend está rodando.\n\nErro: {e}"))
        
        self.run_in_thread(_task)


    def _criar_radio_professores(self, professores):
        """Cria os botões de rádio para professores dinamicamente."""
        # Limpa frames antigos
        for widget in self.chamada_prof_frame.winfo_children(): widget.destroy()
        for widget in self.alunos_prof_frame.winfo_children(): widget.destroy()

        for i, prof in enumerate(professores):
            ctk.CTkRadioButton(self.chamada_prof_frame, text=prof, variable=self.chamada_prof_var, value=prof).grid(row=0, column=i, padx=(0, 15), sticky="w")
            ctk.CTkRadioButton(self.alunos_prof_frame, text=prof, variable=self.alunos_prof_var, value=prof).grid(row=0, column=i, padx=(0, 15), sticky="w")
        
        if professores:
            self.chamada_prof_var.set(professores[0])
            # Por padrão, nenhum professor é selecionado no filtro de alunos
            self.alunos_prof_var.set("")

    def iniciar_busca_alunos(self):
        self.chamada_info_label.configure(text="Buscando dados...")
        # Limpa o grid anterior
        for widget in self.chamada_scroll_frame.winfo_children():
            widget.destroy()
        self.run_in_thread(self.buscar_e_construir_grid)

    def buscar_e_construir_grid(self):
        params = {
            "turma": self.chamada_turma_combo.get(),
            "horario": self.chamada_horario_combo.get(),
            "professor": self.chamada_prof_var.get(),
            "mes": datetime.now().month # Sempre usa o mês vigente para a chamada
        }
        try:
            response = requests.get(f"{API_BASE_URL}/api/alunos", params=params)
            response.raise_for_status()
            self.chamada_data = response.json()

            if not self.chamada_data.get('alunos'):
                self.after(0, lambda: self.chamada_info_label.configure(text="Nenhum aluno encontrado para os filtros selecionados."))
                return

            text = f"Exibindo {len(self.chamada_data['alunos'])} alunos."
            self.after(0, lambda: (self.chamada_info_label.configure(text=text), self.construir_grid()))

        except requests.exceptions.RequestException as e:
            # Atualiza a UI na thread principal para exibir o erro
            error_text = "Erro ao buscar dados."
            self.after(0, lambda: self.chamada_info_label.configure(text=error_text))
            self.after(0, lambda: messagebox.showerror("Erro de API", f"Não foi possível buscar os dados dos alunos.\n\nErro: {e}"))

    def construir_grid(self):
        """Cria a tabela de chamada com base nos dados recebidos."""
        self.chamada_widgets = {}
        
        headers = ['Nível', 'Nome'] + [d.split('/')[0] for d in self.chamada_data['datas']]
        
        # Configura o grid dentro do scrollable frame
        self.chamada_scroll_frame.grid_columnconfigure(1, weight=1) # Coluna do nome

        # Cria os cabeçalhos
        for i, header_text in enumerate(headers):
            header_label = ctk.CTkLabel(self.chamada_scroll_frame, text=header_text, font=ctk.CTkFont(weight="bold"))
            header_label.grid(row=0, column=i, padx=1, pady=1, sticky="ew")

        # Cria as linhas para cada aluno
        for row_idx, aluno in enumerate(self.chamada_data['alunos'], start=1):
            nome_aluno = aluno['Nome']
            
            # Label do Nível
            nivel_label = ctk.CTkLabel(self.chamada_scroll_frame, text=aluno['Nível'])
            nivel_label.grid(row=row_idx, column=0, padx=(5,1), pady=1)

            # Label do Nome
            nome_label = ctk.CTkLabel(self.chamada_scroll_frame, text=nome_aluno, anchor="w")
            nome_label.grid(row=row_idx, column=1, padx=1, pady=1, sticky="ew")

            self.chamada_widgets[nome_aluno] = {}

            # Botões de status
            for col_idx, data_str in enumerate(self.chamada_data['datas'], start=2):
                valor_registrado = aluno.get(data_str, "")
                
                estado_inicial = 0
                for k, v in STATUS_MAP.items():
                    if v["code"] == valor_registrado:
                        estado_inicial = k
                        break
                
                # Usamos uma variável do Tkinter para guardar o estado do botão
                status_var = tk.IntVar(value=estado_inicial)

                btn = ctk.CTkButton(self.chamada_scroll_frame,
                                    text=STATUS_MAP[estado_inicial]["text"],
                                    fg_color=STATUS_MAP[estado_inicial]["fg_color"],
                                    hover_color=STATUS_MAP[estado_inicial]["hover_color"],
                                    width=35, # Largura fixa para evitar o reajuste
                                    text_color="white",
                                    font=ctk.CTkFont(weight="bold"))
                
                # A função de callback precisa de 'lambda' para capturar os valores corretos
                btn.configure(command=lambda v=status_var, b=btn: self.mudar_status(v, b))
                btn.grid(row=row_idx, column=col_idx, padx=1, pady=1)

                self.chamada_widgets[nome_aluno][data_str] = {"var": status_var, "btn": btn}

    def mudar_status(self, status_var, btn_widget):
        """Cicla entre os status quando um botão é clicado."""
        novo_status_id = (status_var.get() + 1) % len(STATUS_MAP)
        status_var.set(novo_status_id)

        # Atualiza a aparência do botão
        novo_estilo = STATUS_MAP[novo_status_id]
        btn_widget.configure(text=novo_estilo["text"], 
                             fg_color=novo_estilo["fg_color"],
                             hover_color=novo_estilo["hover_color"])

    def iniciar_salvar_chamada(self):
        self.chamada_info_label.configure(text="Salvando...")
        self.run_in_thread(self.salvar_chamada)

    def salvar_chamada(self):
        if not self.chamada_widgets:
            messagebox.showwarning("Aviso", "Não há dados de chamada para salvar. Busque os alunos primeiro.")
            self.chamada_info_label.configure(text="Nada para salvar.")
            return

        # Monta payload no formato {"registros": {"Nome": {"dd/mm/yyyy": "c"}}}
        payload = {"registros": {}}

        # Coleta os dados dos widgets
        for aluno in self.chamada_data.get('alunos', []):
            nome_aluno = aluno.get('Nome')
            if not nome_aluno or nome_aluno not in self.chamada_widgets:
                continue

            data_widgets = self.chamada_widgets[nome_aluno]
            for data_str, widget_info in data_widgets.items():
                status_id = widget_info["var"].get()
                status_code = STATUS_MAP[status_id]["code"]
                if status_code:  # Salva apenas se houver um status definido (não vazio)
                    payload["registros"].setdefault(nome_aluno, {})[data_str] = status_code

        if not payload["registros"]:
            messagebox.showinfo("Informação", "Nenhuma alteração detectada para salvar.")
            self.chamada_info_label.configure(text="Nenhuma alteração para salvar.")
            return

        try:
            response = requests.post(f"{API_BASE_URL}/api/chamada", json=payload)
            response.raise_for_status()
            messagebox.showinfo("Sucesso", "Chamada salva com sucesso!")
            self.chamada_info_label.configure(text="Dados salvos com sucesso!")
        except requests.exceptions.RequestException as e:
            messagebox.showerror("Erro ao Salvar", f"Não foi possível salvar os dados na API.\n\nErro: {e}")
            self.chamada_info_label.configure(text="Falha ao salvar.")

    def limpar_conteudo_aba_alunos(self):
        """Limpa os widgets da aba de alunos e mostra uma mensagem padrão."""
        for widget in self.alunos_scroll_frame.winfo_children():
            widget.destroy()
        ctk.CTkLabel(self.alunos_scroll_frame, text="Use os filtros para buscar os alunos e seu histórico.").pack(pady=20)

    def iniciar_busca_todos_alunos(self):
        """Inicia a busca de todos os alunos se o cache estiver vazio."""
        if self.all_students_data is None:
            for widget in self.alunos_scroll_frame.winfo_children():
                widget.destroy()
            ctk.CTkLabel(self.alunos_scroll_frame, text="Buscando dados de todos os alunos...").pack(pady=20)
            self.run_in_thread(self.buscar_e_processar_todos_alunos)
        else:
            # Se já tem cache, apenas exibe
            self.aplicar_filtros_alunos()

    def buscar_e_processar_todos_alunos(self):
        """Busca todos os alunos da API e processa os dados (idade, categoria)."""
        try:
            # CORREÇÃO: Usar um endpoint específico para buscar TODOS os alunos, que não exige parâmetros de filtro.
            response = requests.get(f"{API_BASE_URL}/api/all-alunos")
            response.raise_for_status()
            alunos = response.json()

            # Carrega categorias (sincrono no thread de trabalho) para definir categoria corretamente
            try:
                resp_cats = requests.get(f"{API_BASE_URL}/api/categorias")
                resp_cats.raise_for_status()
                categorias_list = resp_cats.json() or []
            except requests.exceptions.RequestException:
                categorias_list = []

            def definir_categoria_por_idade_local(idade_val):
                if idade_val is None:
                    return 'Não Categorizado'
                # Escolhe a maior 'Idade Mínima' que seja <= idade_val
                sorted_rules = sorted(categorias_list, key=lambda r: r.get('Idade Mínima', 0), reverse=True)
                for regra in sorted_rules:
                    idade_min = regra.get('Idade Mínima', 0)
                    if idade_val >= idade_min:
                        return regra.get('Categoria') or regra.get('Nome da Categoria') or 'Não Categorizado'
                return 'Não Categorizado'

            # Processa cada aluno para adicionar idade e categoria
            for aluno in alunos:
                # Aceita múltiplas variações do nome da coluna de data de nascimento
                data_nasc = aluno.get('Data de Nascimento') or aluno.get('Aniversário') or aluno.get('Aniversario')
                aluno_idade = self._calcular_idade_no_ano(data_nasc)
                aluno['Idade'] = aluno_idade if aluno_idade is not None else ''
                aluno['Categoria'] = definir_categoria_por_idade_local(aluno_idade)

            self.all_students_data = alunos # Armazena a lista processada no cache
            
            # Extrai os níveis únicos da lista de alunos carregada
            niveis_unicos = sorted(list(set(a.get('Nível') for a in alunos if a.get('Nível'))))

            # Após carregar, constrói o grid com TODOS os alunos
            def _update_ui_after_load():
                self.alunos_nivel_combo.configure(values=niveis_unicos) # Popula o filtro de nível
                self._construir_grid_alunos(self.all_students_data)
            self.after(0, _update_ui_after_load)

        except requests.exceptions.RequestException as e:
            # Passa a exceção 'e' para a função de atualização da UI
            self.after(0, self._update_ui_error, e)

    def aplicar_filtros_alunos(self):
        """Filtra os dados dos alunos em cache e reconstrói a grade."""
        if not self.all_students_data:
            self.iniciar_busca_todos_alunos()
            return

        # Coleta os valores dos filtros
        filtro_turma = self.alunos_turma_combo.get()
        filtro_horario = self.alunos_horario_combo.get()
        filtro_prof = self.alunos_prof_var.get()
        filtro_nivel = self.alunos_nivel_combo.get()
        filtro_categoria = self.alunos_categoria_combo.get()

        alunos_filtrados = self.all_students_data

        # Aplica cada filtro
        if filtro_turma: # Só filtra se um valor for selecionado
            alunos_filtrados = [a for a in alunos_filtrados if a.get('Turma') == filtro_turma]
        if filtro_horario:
            alunos_filtrados = [a for a in alunos_filtrados if a.get('Horário') == filtro_horario]
        if filtro_prof:
            alunos_filtrados = [a for a in alunos_filtrados if a.get('Professor') == filtro_prof]
        if filtro_nivel:
            alunos_filtrados = [a for a in alunos_filtrados if a.get('Nível') == filtro_nivel]
        if filtro_categoria:
            alunos_filtrados = [a for a in alunos_filtrados if a.get('Categoria') == filtro_categoria]

        self._construir_grid_alunos(alunos_filtrados)

    def limpar_filtros_alunos(self):
        """Reseta todos os filtros da aba Alunos para o estado padrão."""
        self.alunos_turma_combo.set("")
        self.alunos_horario_combo.set("")
        self.alunos_prof_var.set("") # Desseleciona os radio buttons de professor
        self.alunos_nivel_combo.set("")
        self.alunos_categoria_combo.set("")
        # Após limpar, aplica os filtros para atualizar a lista (mostrando todos)
        self.aplicar_filtros_alunos()

    def _construir_grid_alunos(self, alunos_para_exibir):
        """Constrói a grade de exibição na aba 'Alunos'."""
        for widget in self.alunos_scroll_frame.winfo_children():
            widget.destroy()

        if not alunos_para_exibir:
            ctk.CTkLabel(self.alunos_scroll_frame, text="Nenhum aluno encontrado para os filtros selecionados.").pack(pady=20)
            return

        frame = self.alunos_scroll_frame

        # Cabeçalhos (ordenados: Nome, depois Nível)
        headers = ['Nome', 'Nível', 'Idade', 'Categoria', 'Turma', 'Horário', 'Professor']
        # Maior peso para a coluna Nome, pequeno peso para Nível, demais fixos
        frame.grid_columnconfigure(0, weight=2)
        frame.grid_columnconfigure(1, weight=1)
        for col in range(2, len(headers)):
            frame.grid_columnconfigure(col, weight=0)

        header_labels = []
        for i, header_text in enumerate(headers):
            # Fonte dos cabeçalhos reduzida em ~2pt para melhor densidade
            # Alinha o cabeçalho 'Nome' à esquerda
            anchor = 'w' if header_text == 'Nome' else 'center'
            pad = (10, 5) if header_text == 'Nome' else (5, 5)
            header_label = ctk.CTkLabel(frame, text=header_text, font=ctk.CTkFont(size=12, weight="bold"), anchor=anchor)
            sticky_val = 'w' if anchor == 'w' else 'ew'
            header_label.grid(row=0, column=i, padx=pad, pady=4, sticky=sticky_val)
            header_labels.append(header_label)

        # Linhas de Alunos
        for row_idx, aluno in enumerate(alunos_para_exibir, start=1):
            # Coluna 0: Nome (menos espaçamento à direita para aproximar do Nível)
            name_lbl = ctk.CTkLabel(frame, text=aluno.get('Nome', ''), anchor="w")
            name_lbl.grid(row=row_idx, column=0, padx=(10,3), pady=2, sticky="w")
            # Coluna 1: Nível (centralizada)
            nivel_lbl = ctk.CTkLabel(frame, text=aluno.get('Nível', ''), anchor="center")
            nivel_lbl.grid(row=row_idx, column=1, padx=(3,10), pady=2, sticky="ew")
            ctk.CTkLabel(frame, text=str(aluno.get('Idade', '')), anchor="center").grid(row=row_idx, column=2, padx=5, pady=2, sticky="ew")
            ctk.CTkLabel(frame, text=aluno.get('Categoria', ''), anchor="center").grid(row=row_idx, column=3, padx=5, pady=2, sticky="ew")
            ctk.CTkLabel(frame, text=aluno.get('Turma', ''), anchor="center").grid(row=row_idx, column=4, padx=5, pady=2, sticky="ew")
            ctk.CTkLabel(frame, text=aluno.get('Horário', ''), anchor="center").grid(row=row_idx, column=5, padx=5, pady=2, sticky="ew")
            ctk.CTkLabel(frame, text=aluno.get('Professor', ''), anchor="center").grid(row=row_idx, column=6, padx=5, pady=2, sticky="ew")

        # Auto-ajusta largura mínima por coluna com base no conteúdo (como Excel)
        try:
            col_count = len(headers)
            max_widths = [0] * col_count

            # medir cabeçalhos
            for i, lbl in enumerate(header_labels):
                f = tkfont.Font(font=lbl.cget('font'))
                w = f.measure(str(lbl.cget('text')))
                max_widths[i] = max(max_widths[i], w)

            # medir conteúdo: primeiro 50 linhas para eficiência
            sample = alunos_para_exibir[:50]
            keys = ['Nome','Nível','Idade','Categoria','Turma','Horário','Professor']
            for row in sample:
                for i in range(col_count):
                    key = keys[i]
                    text = str(row.get(key, ''))
                    f = tkfont.Font(size=11)
                    w = f.measure(text)
                    if w > max_widths[i]:
                        max_widths[i] = w

            # aplica minsize com um padding extra
            for i, w in enumerate(max_widths):
                min_px = int(w + 24)
                frame.grid_columnconfigure(i, minsize=min_px)
        except Exception:
            pass

    def _calcular_idade_no_ano(self, data_nasc_str):
        """Calcula a idade que o aluno fará no ano corrente."""
        if not data_nasc_str:
            return None

        # Se já for um objeto datetime
        if isinstance(data_nasc_str, datetime):
            ano_corrente = datetime.now().year
            return ano_corrente - data_nasc_str.year

        data_text = str(data_nasc_str)
        # Tenta formatos possíveis: dd/mm/YYYY, ISO (YYYY-mm-ddT...), ou apenas YYYY-mm-dd
        for fmt in ('%d/%m/%Y', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d'):
            try:
                parsed = datetime.strptime(data_text.split('T')[0] if 'T' in data_text else data_text, fmt.split('T')[0])
                ano_corrente = datetime.now().year
                return ano_corrente - parsed.year
            except (ValueError, TypeError):
                continue

        # Tenta parse flexível (sem dependências adicionais)
        try:
            parsed_iso = datetime.fromisoformat(data_text)
            ano_corrente = datetime.now().year
            return ano_corrente - parsed_iso.year
        except Exception:
            return None

    def _definir_categoria(self, idade):
        """Define a categoria do aluno com base na idade e nos dados de categoria em cache."""
        if idade is None or self.categorias_data is None:
            return 'Não Categorizado'
        
        categoria_adequada = 'Não Categorizado'
        for cat in self.categorias_data:
            if idade >= cat.get('Idade Mínima', 0):
                categoria_adequada = cat.get('Nome da Categoria') or cat.get('Categoria') or categoria_adequada
            else:
                break # Como a lista está ordenada, podemos parar
        return categoria_adequada

    def carregar_categorias(self):
        """Busca as categorias da API e as armazena em cache."""
        try:
            response = requests.get(f"{API_BASE_URL}/api/categorias")
            response.raise_for_status()
            # Ordena da maior idade mínima para a menor para facilitar a lógica de definição
            categorias = response.json()
            def _update_ui():
                # Normaliza nomes e garante que chaves esperadas existam
                self.categorias_data = sorted(categorias, key=lambda x: x.get('Idade Mínima', 0), reverse=True)
                nomes_categorias = [cat.get('Nome da Categoria') or cat.get('Categoria') or 'Não Categorizado' for cat in sorted(categorias, key=lambda x: x.get('Idade Mínima', 0))]
                self.alunos_categoria_combo.configure(values=nomes_categorias)
                self.alunos_categoria_combo.set("")
            self.after(0, _update_ui)
        except requests.exceptions.RequestException as e:
            print(f"Erro ao carregar categorias: {e}")
            self.after(0, lambda: self.alunos_categoria_combo.configure(values=["Erro ao carregar"]))

    def _update_ui_error(self, error_message):
        """Limpa um frame e exibe uma mensagem de erro nele."""
        for widget in self.alunos_scroll_frame.winfo_children():
            widget.destroy()
        ctk.CTkLabel(self.alunos_scroll_frame, text=f"Erro ao carregar a lista de alunos: {error_message}").pack(pady=20)

    def carregar_lista_turmas(self):
        """Busca e exibe a lista de turmas com botões de atalho."""
        for widget in self.turmas_scroll_frame.winfo_children():
            widget.destroy()

        try:
            response = requests.get(f"{API_BASE_URL}/api/all-turmas")
            response.raise_for_status()
            turmas = response.json()

            headers = ["Nível", "Turma", "Horário", "Professor", "Data de Início", "Qtd.", "Atalho"]
            self.turmas_scroll_frame.grid_columnconfigure(0, weight=1)
            self.turmas_scroll_frame.grid_columnconfigure(1, weight=1)
            self.turmas_scroll_frame.grid_columnconfigure(2, weight=1)
            self.turmas_scroll_frame.grid_columnconfigure(3, weight=1)
            self.turmas_scroll_frame.grid_columnconfigure(4, weight=1)

            for i, header in enumerate(headers):
                # Centraliza o cabeçalho da quantidade
                anchor = "center" if header == "Qtd." else "w"
                ctk.CTkLabel(self.turmas_scroll_frame, text=header, font=ctk.CTkFont(weight="bold"), anchor=anchor).grid(row=0, column=i, padx=5, pady=5, sticky="ew")

            for row_idx, turma in enumerate(turmas, start=1):
                ctk.CTkLabel(self.turmas_scroll_frame, text=turma.get("Nível", ""), anchor="w").grid(row=row_idx, column=0, padx=5, pady=5, sticky="ew")
                ctk.CTkLabel(self.turmas_scroll_frame, text=turma.get("Turma", ""), anchor="w").grid(row=row_idx, column=1, padx=5, pady=5, sticky="ew")
                ctk.CTkLabel(self.turmas_scroll_frame, text=turma.get("Horário", ""), anchor="w").grid(row=row_idx, column=2, padx=5, pady=5, sticky="ew")
                ctk.CTkLabel(self.turmas_scroll_frame, text=turma.get("Professor", ""), anchor="w").grid(row=row_idx, column=3, padx=5, pady=5, sticky="ew")
                ctk.CTkLabel(self.turmas_scroll_frame, text=turma.get("Data de Início", ""), anchor="w").grid(row=row_idx, column=4, padx=5, pady=5, sticky="ew")
                ctk.CTkLabel(self.turmas_scroll_frame, text=str(turma.get("qtd.", 0)), anchor="center").grid(row=row_idx, column=5, padx=5, pady=5, sticky="ew")
                
                # Botão de atalho com ícone
                atalho_btn = ctk.CTkButton(self.turmas_scroll_frame, text="»", width=40, font=ctk.CTkFont(size=16, weight="bold"))
                atalho_btn.configure(command=lambda t=turma: self.usar_atalho_turma(t))
                atalho_btn.grid(row=row_idx, column=6, padx=5, pady=5)

        except requests.exceptions.RequestException as e:
            ctk.CTkLabel(self.turmas_scroll_frame, text=f"Erro ao carregar turmas: {e}").pack()

    def usar_atalho_turma(self, turma_info: dict):
        """Preenche os filtros e muda para a aba de chamada."""
        # Garante que a sidebar esteja aberta para mostrar o menu de controle
        if not self.sidebar_is_open:
            self.toggle_sidebar()

        # 1. Mudar para a view de Chamada (isso vai mostrar o menu de controle correto)
        self.show_view("Chamada")

        # 2. Preencher os filtros no menu de controle da chamada
        self.chamada_turma_combo.set(turma_info.get("Turma", ""))
        self.chamada_horario_combo.set(turma_info.get("Horário", ""))
        self.chamada_prof_var.set(turma_info.get("Professor", ""))

        # 3. Iniciar a busca de alunos automaticamente
        self.iniciar_busca_alunos()

if __name__ == "__main__":
    # --- Instalação de Dependências ---
    try:
        import customtkinter
        import requests
    except ImportError:
        import subprocess
        import sys
        print("Instalando dependências necessárias (customtkinter, requests)...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "customtkinter", "requests"])
        print("Dependências instaladas. Por favor, rode o script novamente.")
        sys.exit()

    app = App()
    app.mainloop()
