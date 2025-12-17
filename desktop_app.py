import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox
import json
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

class SearchableEntry(ctk.CTkEntry):
    """Um CTkEntry que mostra sugestões em uma Toplevel window."""
    def __init__(self, master, suggestions_list=None, **kwargs):
        super().__init__(master, **kwargs)
        self.suggestions_list = suggestions_list or []
        self._suggestions_toplevel = None
        self._suggestions_frame = None
        self._active_suggestion_index = -1
        self._suggestion_labels = []

        self.bind("<KeyRelease>", self._on_key_release)
        self.bind("<Down>", self._on_arrow_down)
        self.bind("<Up>", self._on_arrow_up)
        self.bind("<Return>", self._on_enter)
        self.bind("<Escape>", lambda e: self._hide_suggestions())
        self.bind("<FocusOut>", lambda e: self.after(200, self._hide_suggestions_if_not_focused))

    def _on_key_release(self, event):
        if event.keysym in ("Down", "Up", "Return", "Escape"):
            return

        query = self.get().lower()
        if not query:
            self._hide_suggestions()
            return

        filtered_suggestions = [s for s in self.suggestions_list if query in s.lower()]
        if filtered_suggestions:
            self._show_suggestions(filtered_suggestions)
        else:
            self._hide_suggestions()

    def _show_suggestions(self, suggestions):
        if self._suggestions_toplevel is None:
            x = self.winfo_rootx()
            y = self.winfo_rooty() + self.winfo_height()
            self._suggestions_toplevel = tk.Toplevel(self)
            self._suggestions_toplevel.wm_overrideredirect(True)
            self._suggestions_toplevel.wm_geometry(f"+{x}+{y}")
            self._suggestions_frame = ctk.CTkFrame(self._suggestions_toplevel, corner_radius=5)
            self._suggestions_frame.pack(expand=True, fill="both")

        for widget in self._suggestions_frame.winfo_children():
            widget.destroy()

        self._suggestion_labels = []
        for i, text in enumerate(suggestions):
            label = ctk.CTkLabel(self._suggestions_frame, text=text, anchor="w", corner_radius=5)
            label.pack(fill="x", padx=5, pady=2)
            label.bind("<Enter>", lambda e, index=i: self._highlight_suggestion(index))
            label.bind("<Button-1>", lambda e, t=text: self._select_suggestion(t))

        self._active_suggestion_index = -1
        self._suggestion_labels = self._suggestions_frame.winfo_children()
        self._suggestions_toplevel.lift()

    def _hide_suggestions(self):
        if self._suggestions_toplevel:
            self._suggestions_toplevel.destroy()
            self._suggestions_toplevel = None
            self._suggestions_frame = None

    def _hide_suggestions_if_not_focused(self):
        """Esconde as sugestões se nem o entry nem a lista de sugestões estiverem em foco."""
        try:
            focused_widget = self.winfo_toplevel().focus_get()
            if focused_widget != self and (self._suggestions_toplevel is None or focused_widget not in self._suggestions_toplevel.winfo_children()):
                self._hide_suggestions()
        except (KeyError, tk.TclError): # Pode dar erro se a janela for destruída
            self._hide_suggestions()

    def _highlight_suggestion(self, index):
        """Destaca uma sugestão na lista."""
        for i, label in enumerate(self._suggestion_labels):
            if i == index:
                label.configure(fg_color=("#d3d3d3", "#555555")) # Cor de destaque
            else:
                label.configure(fg_color="transparent")
        self._active_suggestion_index = index

    def _on_arrow_down(self, event):
        if not self._suggestions_toplevel or not self._suggestion_labels: return
        new_index = (self._active_suggestion_index + 1) % len(self._suggestion_labels)
        self._highlight_suggestion(new_index)

    def _on_arrow_up(self, event):
        if not self._suggestions_toplevel or not self._suggestion_labels: return
        new_index = (self._active_suggestion_index - 1)
        if new_index < 0: new_index = len(self._suggestion_labels) - 1
        self._highlight_suggestion(new_index)

    def _on_enter(self, event):
        if self._suggestions_toplevel and self._active_suggestion_index != -1:
            self._select_suggestion(self._suggestion_labels[self._active_suggestion_index].cget("text"))

    def _select_suggestion(self, text):
        self.delete(0, "end")
        self.insert(0, text)
        self._hide_suggestions()

class ColumnResizer(ctk.CTkFrame):
    """Um widget separador que permite redimensionar uma coluna de um grid."""
    def __init__(self, master, grid_layout, column_index, app_instance):
        # A largura do frame define a área clicável. O cursor indica a funcionalidade.
        super().__init__(master, width=7, cursor="sb_h_double_arrow", fg_color="transparent")
        self.grid_layout = grid_layout
        self.column_index = column_index
        self._start_x = 0
        self._start_width = 0

        self.app = app_instance # Armazena a referência da aplicação principal
        self.bind("<Button-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)

    def _on_press(self, event):
        # Adiciona verificação do modo de edição do app principal
        if not self.app.alunos_grid_edit_mode.get():
            return

        self._start_x = event.x_root
        # Obtém a largura mínima atual da coluna que será redimensionada
        self._start_width = self.grid_layout.grid_columnconfigure(self.column_index)['minsize']

    def _on_drag(self, event):
        delta_x = event.x_root - self._start_x
        new_width = max(10, self._start_width + delta_x) # Garante uma largura mínima de 10px
        # Adiciona verificação do modo de edição do app principal
        if not self.app.alunos_grid_edit_mode.get():
            return

        self.grid_layout.grid_columnconfigure(self.column_index, minsize=new_width)

class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Gerenciador de Chamadas")
        self.geometry("1200x700")
        ctk.set_appearance_mode("System")
        self.protocol("WM_DELETE_WINDOW", self._on_app_close) # Salva config ao fechar

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

        # --- 2. ÁREA PRINCIPAL (MAIN CONTENT) ---
        self.main_content_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.main_content_frame.grid(row=0, column=1, rowspan=2, sticky="nsew", padx=0, pady=0) # Ocupa as linhas 0 e 1
        self.main_content_frame.grid_rowconfigure(0, weight=1)
        self.main_content_frame.grid_columnconfigure(0, weight=1)

        # --- 2.1. Criação da TabView ---
        self.tab_view = ctk.CTkTabview(self.main_content_frame, corner_radius=8)
        self.tab_view.grid(row=0, column=0, padx=20, pady=(0, 20), sticky="nsew")
        self.tab_view.add("Chamada")

        self.tab_view.add("Alunos")
        self.tab_view.add("Turmas")
        self.tab_view.set("Chamada") 

        # --- Botão Adicionar Aluno (canto superior direito, sobreposto) ---
        # Movido para ser filho da janela principal (self) para não ser coberto pelo tab_view
        self.add_student_button = ctk.CTkButton(self, text="+ Adicionar Aluno", command=self.open_add_student_window)
        self.add_student_button.place(relx=1.0, rely=0.0, x=-20, y=10, anchor="ne")

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
        # Configura o grid da aba Alunos para ter uma linha para a busca e outra para a lista
        self.tab_view.tab("Alunos").grid_columnconfigure(0, weight=1)
        self.tab_view.tab("Alunos").grid_rowconfigure(0, weight=0) # Linha da busca (altura fixa)
        self.tab_view.tab("Alunos").grid_columnconfigure(1, weight=0) # Coluna para o botão 'x'
        self.tab_view.tab("Alunos").grid_rowconfigure(1, weight=1) # Linha da lista (expansível)

        # Widget de busca por nome na aba Alunos
        self.alunos_search_entry = ctk.CTkEntry(self.tab_view.tab("Alunos"), placeholder_text="Buscar por nome...")
        self.alunos_search_entry.grid(row=0, column=0, padx=10, pady=10, sticky="w")
        self.alunos_search_entry.bind("<KeyRelease>", self.filtrar_alunos_por_nome)
        
        # --- Frame para os botões de controle da grade de alunos ---
        alunos_grid_controls_frame = ctk.CTkFrame(self.tab_view.tab("Alunos"), fg_color="transparent")
        alunos_grid_controls_frame.grid(row=0, column=1, padx=(0, 10), pady=10, sticky="e")
        
        # Botão para ativar/desativar a edição da grade
        button_width = 60 # Largura padrão para os botões
        self.alunos_grid_edit_mode = tk.BooleanVar(value=False)
        self.edit_grid_button = ctk.CTkButton(alunos_grid_controls_frame, text="Editar Layout",
                                              width=button_width,
                                              font=ctk.CTkFont(size=9),
                                              command=self._toggle_grid_edit_mode)
        self.edit_grid_button.pack(side="left", padx=(0, 5))
        self._update_edit_button_color() # Define a cor inicial
        
        # Botão para limpar todos os filtros e ordenação
        self.clear_all_filters_sort_button = ctk.CTkButton(alunos_grid_controls_frame, text="Limpar Filtros",
                                                            width=button_width,
                                                            font=ctk.CTkFont(size=9),
                                                            command=self._clear_all_filters_and_sort,
                                                            fg_color="transparent", border_width=1)
        self.clear_all_filters_sort_button.pack(side="left")

        # Scroll frame para a lista de alunos
        self.alunos_scroll_frame = ctk.CTkScrollableFrame(self.tab_view.tab("Alunos"), label_text="Cadastro Geral de Alunos")
        self.alunos_scroll_frame.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=10, pady=(0, 10))

        # --- 2.4. Conteúdo da Aba "Turmas" ---
        self.tab_view.tab("Turmas").grid_columnconfigure(0, weight=1)
        self.tab_view.tab("Turmas").grid_rowconfigure(0, weight=1)
        self.turmas_scroll_frame = ctk.CTkScrollableFrame(self.tab_view.tab("Turmas"), label_text="Lista de Turmas e Atalhos")
        self.turmas_scroll_frame.grid(row=0, column=0, sticky="nsew")

        # --- ARMAZENAMENTO DE ESTADO ---
        self.sidebar_is_open = True
        meses = [datetime(2000, i, 1).strftime('%B') for i in range(1, 13)]
        self.alunos_sort_state = {'key': None, 'reverse': False} # Para ordenação da lista de alunos
        self.alunos_filter_state = {} # Para filtros por coluna
        self.chamada_data = {} # Guarda os dados da API
        self.chamada_widgets = {} # Guarda os widgets de botão para poder ler o estado
        self.all_students_data = None # Cache para todos os alunos
        self.categorias_data = None # Cache para as categorias
        self.turmas_data = None # Cache para os dados das turmas (usado para encontrar o nível)
        self.active_filter_menu = None # Referência ao menu de filtro ativo
        self.add_student_toplevel = None # Referência para a janela de adicionar aluno
        self.edit_student_toplevel = None # Referência para a janela de editar aluno
        self.filter_menu_geometry_cache = {} # Cache para a geometria dos menus de filtro
        self.column_widths_cache = {} # Cache para a largura das colunas da aba Alunos
        self.last_student_add_data = {} # Guarda os últimos dados para preenchimento
        self.alunos_grid_resizers = [] # Lista para guardar os widgets de redimensionamento
        
        # Mapeamento de views para seus frames de controle
        self.control_frames = {
            "Chamada": self.chamada_control_frame,
        }

        # --- INICIALIZAÇÃO ---
        self.carregar_filtros_iniciais()
        self._load_config() # Carrega as configurações salvas
        self.run_in_thread(self.carregar_lista_turmas) # Carrega dados de turmas em background para o form
        self.show_main_menu() # Garante que o menu principal seja exibido no início

    def _load_config(self):
        """Carrega configurações do app de um arquivo JSON."""
        try:
            with open("config.json", "r") as f:
                config = json.load(f)
                self.column_widths_cache = config.get("column_widths", {})

                self.filter_menu_geometry_cache = config.get("filter_menu_geometry", {})
        except (FileNotFoundError, json.JSONDecodeError):
            self.column_widths_cache = {} # Se o arquivo não existe ou está corrompido, usa o padrão
            self.filter_menu_geometry_cache = {}

    def _save_config(self):
        """Salva as configurações atuais do app em um arquivo JSON."""
        # Só salva se o modo de edição estiver habilitado, para evitar salvar em estado "fixo"
        if self.alunos_grid_edit_mode.get():
            # 1. Carrega a configuração existente para não sobrescrever dados não relacionados.
            try:
                with open("config.json", "r") as f:
                    config = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                config = {}

            # 2. Atualiza a largura das colunas da aba Alunos no dicionário de config
            if self.alunos_scroll_frame.winfo_exists():
                headers = ['Nome', 'Nível', 'Idade', 'Categoria', 'Turma', 'Horário', 'Professor', '']
                current_widths = {headers[i]: self.alunos_scroll_frame.grid_columnconfigure(i)['minsize'] for i in range(len(headers))}
                config["column_widths"] = current_widths

            # 3. Atualiza a geometria dos menus de filtro no dicionário de config
            config["filter_menu_geometry"] = self.filter_menu_geometry_cache

            # 4. Salva o dicionário de configuração completo no arquivo
            with open("config.json", "w", encoding='utf-8') as f:
                json.dump(config, f, indent=4)

    def _on_app_close(self):
        """Executa ações de salvamento antes de fechar o app."""
        self._save_config()
        self.destroy()

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
            # Recolhe o menu ao selecionar "Alunos"
            if self.sidebar_is_open:
                self.toggle_sidebar()
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
                    
                    # Ordena os horários (ex: "08:00-09:00")
                    horarios_brutos = data.get('horarios', []) or []
                    horarios_ordenados = sorted(horarios_brutos, key=lambda h: (int(h.split(':')[0]), int(h.split(':')[1].split('-')[0])) if ':' in h else h)

                    self.chamada_turma_combo.configure(values=turmas)
                    self.chamada_turma_combo.set(turmas[0] if turmas else "")
                    self.chamada_horario_combo.configure(values=horarios_ordenados)
                    self.chamada_horario_combo.set(horarios_ordenados[0] if horarios_ordenados else "")
                    professores = data.get('professores', [])
                    self._criar_radio_professores(professores)
                self.after(0, _update_ui) # Agenda a atualização da UI

            except requests.exceptions.RequestException as e:
                self.after(0, lambda: messagebox.showerror("Erro de Conexão", f"Não foi possível carregar os filtros da API.\nVerifique se o backend está rodando.\n\nErro: {e}"))
        
        self.run_in_thread(_task)


    def _criar_radio_professores(self, professores):
        """Cria os botões de rádio para professores dinamicamente."""
        # Limpa frames antigos
        for widget in self.chamada_prof_frame.winfo_children(): widget.destroy()

        for i, prof in enumerate(professores):
            ctk.CTkRadioButton(self.chamada_prof_frame, text=prof, variable=self.chamada_prof_var, value=prof).grid(row=0, column=i, padx=(0, 15), sticky="w")
        
        if professores:
            self.chamada_prof_var.set(professores[0])

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
            self.filtrar_alunos_por_nome() # Apenas filtra a lista existente

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
                if idade_val is None or not categorias_list:
                    return 'Não Categorizado'
                # Escolhe a maior 'Idade Mínima' que seja <= idade_val
                sorted_rules = sorted(categorias_list, key=lambda r: r.get('Idade Mínima', 0), reverse=True)
                for regra in sorted_rules:
                    idade_min = regra.get('Idade Mínima', 0)
                    if idade_val >= idade_min:
                        # Prioriza 'Nome da Categoria' se existir
                        return regra.get('Nome da Categoria') or regra.get('Categoria') or 'Não Categorizado'
                return 'Não Categorizado'

            # Processa cada aluno para adicionar idade e categoria
            for idx, aluno in enumerate(alunos):
                # Normaliza os dados do aluno para consistência interna
                aluno_normalizado = self._normalizar_dados_aluno(aluno, categorias_list)
                alunos[idx] = aluno_normalizado

            self.all_students_data = alunos # Armazena a lista processada e normalizada no cache

            
            # Após carregar, constrói o grid com TODOS os alunos
            def _update_ui_after_load():
                self._construir_grid_alunos(self.all_students_data)
            self.after(0, _update_ui_after_load)

        except requests.exceptions.RequestException as e:
            # Passa a exceção 'e' para a função de atualização da UI
            self.after(0, self._update_ui_error, e)

    def _normalizar_dados_aluno(self, aluno_data, categorias_list):
        """
        Centraliza a lógica de limpeza e padronização dos dados de um aluno.
        Garante que chaves conflitantes (ex: 'Aniversario' vs 'Data de Nascimento') sejam unificadas.
        """
        # 1. Unifica a data de nascimento
        data_nasc_val = aluno_data.get('Aniversario') or aluno_data.get('Aniversário') or aluno_data.get('Data de Nascimento')
        aluno_data['Aniversario'] = data_nasc_val

        # 2. Unifica o telefone/whatsapp
        telefone_val = aluno_data.get('Whatsapp') or aluno_data.get('Telefone')
        aluno_data['Whatsapp'] = telefone_val

        # 3. Calcula e adiciona Idade
        idade = self._calcular_idade_no_ano(data_nasc_val)
        aluno_data['Idade'] = idade if idade is not None else ''

        # 4. Define e adiciona Categoria
        def definir_categoria(idade_val):
            if idade_val is None or not categorias_list:
                return 'Não Categorizado'
            sorted_rules = sorted(categorias_list, key=lambda r: r.get('Idade Mínima', 0), reverse=True)
            for regra in sorted_rules:
                idade_min = regra.get('Idade Mínima', 0)
                if idade_val >= idade_min:
                    return regra.get('Nome da Categoria') or regra.get('Categoria') or 'Não Categorizado'
            return 'Não Categorizado'

        aluno_data['Categoria'] = definir_categoria(idade)

        # Remove chaves antigas/conflitantes para evitar ambiguidade
        aluno_data.pop('Data de Nascimento', None)
        aluno_data.pop('Telefone', None)
        return aluno_data
            
    def filtrar_alunos_por_nome(self, event=None):
        """Filtra a lista de alunos na aba 'Alunos' com base no texto da caixa de busca."""
        if not self.all_students_data:
            return # Não faz nada se os dados ainda não foram carregados

        query = self.alunos_search_entry.get().lower()
        
        # Aplica filtro de busca por nome
        alunos_filtrados_nome = [aluno for aluno in self.all_students_data if query in aluno.get('Nome', '').lower()] if query else self.all_students_data

        # Aplica filtros de coluna (do menu)
        alunos_filtrados = self._apply_column_filters(alunos_filtrados_nome)

        # Reconstrói o grid com os dados duplamente filtrados
        self._construir_grid_alunos(alunos_filtrados)

    def _clear_all_filters_and_sort(self):
        """Reseta o estado de ordenação e todos os filtros, e reconstrói a grade."""
        self.alunos_sort_state = {'key': None, 'reverse': False}
        self.alunos_filter_state = {}
        # Limpa o texto da busca para garantir que todos os alunos sejam exibidos após a limpeza
        self.alunos_search_entry.delete(0, "end")
        self.filtrar_alunos_por_nome()

    def _toggle_grid_edit_mode(self):
        """Ativa ou desativa o modo de edição da grade de alunos."""
        is_currently_editing = self.alunos_grid_edit_mode.get()
        # Se o modo de edição estava ATIVO e será desativado, salva as configurações.
        if is_currently_editing:
            self._save_config()
        self.alunos_grid_edit_mode.set(not self.alunos_grid_edit_mode.get())

        self._update_edit_button_color()

    def _update_edit_button_color(self):
        """Atualiza a cor do botão de edição para indicar se está ativo."""
        if self.alunos_grid_edit_mode.get():
            # Cor padrão de botão ativo
            self.edit_grid_button.configure(fg_color=("#3b8ed0", "#1f6aa5"), border_width=0)
        else:
            # Estilo "outline" para quando estiver inativo
            self.edit_grid_button.configure(fg_color="transparent", border_width=1)

    def _apply_column_filters(self, data_list):
        """Aplica os filtros de coluna definidos em self.alunos_filter_state."""
        if not self.alunos_filter_state:
            return data_list

        filtered_data = data_list
        for key, selected_values in self.alunos_filter_state.items():
            if not selected_values: continue # Se o conjunto de valores estiver vazio, ignora o filtro
            
            filtered_data = [item for item in filtered_data if item.get(key) in selected_values]

        return filtered_data

    def _construir_grid_alunos(self, alunos_para_exibir):
        """Constrói a grade de exibição na aba 'Alunos'."""
        for widget in self.alunos_scroll_frame.winfo_children():
            widget.destroy()
        self.alunos_grid_resizers.clear() # Limpa a lista de resizers antigos

        if not alunos_para_exibir:
            ctk.CTkLabel(self.alunos_scroll_frame, text="Nenhum aluno encontrado.").pack(pady=20)
            return

        # --- Lógica de Ordenação ---
        sort_key = self.alunos_sort_state.get('key')
        sort_reverse = self.alunos_sort_state.get('reverse', False)

        # --- Lógica de Ordenação ---
        if sort_key:
            # Mapeamentos para ordenação customizada
            nivel_order = {
                'Iniciação B': 0, 'Iniciação A': 1, 'Nível 1': 2, 'Nível 2': 3,
                'Nível 3': 4, 'Nível 4': 5, 'Adulto B': 6, 'Adulto A': 7
            }
            categoria_order = {
                'Pré-Mirim': 0, 'Mirim I': 1, 'Mirim II': 2, 'Petiz I': 3, 'Petiz II': 4,
                'Infantil I': 5, 'Infantil II': 6, 'Juvenil I': 7, 'Juvenil II': 8,
                'Júnior I': 9, 'Júnior II/Sênior': 10
            }

            def get_sort_value(aluno):
                val = aluno.get(sort_key, '')
                if val is None: val = ''

                if sort_key == 'Nível':
                    return nivel_order.get(val, 99) # Valores não mapeados vão para o final
                if sort_key == 'Categoria':
                    # Extrai a parte principal da categoria (ex: "Mirim" de "Mirim I")
                    main_cat = val.split(' ')[0]
                    # Usa a ordem do dicionário, com um valor alto para categorias não listadas (A...M)
                    # e adiciona um sub-valor para ordenar dentro da mesma categoria (ex: Mirim I vs Mirim II)
                    order_val = categoria_order.get(val, categoria_order.get(main_cat, 99))
                    return (order_val, val)
                if sort_key == 'Idade':
                    return int(val) if str(val).isdigit() else 0
                if sort_key == 'Horário':
                    return val.split('-')[0]
                return str(val).lower()

            alunos_para_exibir = sorted(alunos_para_exibir, key=get_sort_value, reverse=sort_reverse)

        # O frame onde os widgets serão colocados é o próprio CTkScrollableFrame.
        frame = self.alunos_scroll_frame
        headers = ['Nome', 'Nível', 'Idade', 'Categoria', 'Turma', 'Horário', 'Professor', ''] # Adicionado espaço para ações
        
        # Define as larguras iniciais. O usuário poderá ajustá-las manualmente.
        initial_widths = {'Nome': 250, 'Nível': 80, 'Idade': 50, 'Categoria': 100, 'Turma': 100, 'Horário': 100, 'Professor': 120, '': 80}
        for i, header_text in enumerate(headers):
            # Usa a largura do cache se existir, senão usa a largura inicial padrão
            width = self.column_widths_cache.get(header_text, initial_widths.get(header_text, 80))
            
            # Define o peso como 0 para desativar o auto-ajuste.
            weight = 0
            # Define a configuração para cada coluna sequencial (0, 1, 2, ...)
            frame.grid_columnconfigure(i, weight=weight, minsize=width)

        def create_header_widget(text, key):
            """
            Cria um Label para o cabeçalho. Se o cabeçalho estiver ativo (ordenado/filtrado),
            cria um Botão para indicar visualmente. Isso permite que colunas inativas
            sejam muito mais estreitas, pois Labels têm menos largura intrínseca.
            """
            display_text = text
            is_active = self.alunos_sort_state.get('key') == key or (key in self.alunos_filter_state and self.alunos_filter_state[key])

            if self.alunos_sort_state.get('key') == key:
                sort_arrow = '▼' if self.alunos_sort_state.get('reverse') else '▲'
                display_text = f"{text} {sort_arrow}"
            elif key in self.alunos_filter_state and self.alunos_filter_state[key]:
                display_text += " ▾" # Um ícone simples para indicar filtro

            # Se estiver ativo, usa um botão para dar feedback visual. Senão, um label.
            if is_active:
                widget = ctk.CTkButton(frame, text=display_text,
                                     fg_color=("#e0e2e4", "#4a4d50"), hover_color=("#d3d5d7", "#5a5d60"),
                                     text_color=("gray10", "gray90"), font=ctk.CTkFont(size=12, weight="bold"))
            else:
                widget = ctk.CTkLabel(frame, text=display_text,
                                    font=ctk.CTkFont(size=12, weight="bold"),
                                    text_color=("gray10", "gray90"))
                # Adiciona um bind para que o label se comporte como um botão ao clicar
                widget.bind("<Button-1>", lambda e, k=key, w=widget: self._open_filter_menu(k, w))

            # O comando para abrir o menu é configurado separadamente para o botão
            if isinstance(widget, ctk.CTkButton):
                widget.configure(command=lambda k=key, w=widget: self._open_filter_menu(k, w))

            return widget

        for i, header_text in enumerate(headers):
            if not header_text: # Cabeçalho da coluna de ações
                ctk.CTkLabel(self.alunos_scroll_frame, text="Ações", font=ctk.CTkFont(size=12, weight="bold")).grid(row=0, column=i, padx=2, pady=4, sticky='ns')
                continue

            key = header_text
            header_widget = create_header_widget(header_text, key)
            # Usa sticky="ns" para centralizar verticalmente e permitir que o resizer ocupe o espaço horizontal.
            header_widget.grid(row=0, column=i, padx=0, pady=4, sticky='ns')

            # Adiciona um redimensionador após cada cabeçalho, exceto o último
            if i < len(headers) - 1:
                resizer = ColumnResizer(frame, grid_layout=frame, column_index=i, app_instance=self) 
                resizer.grid(row=0, column=i, rowspan=len(alunos_para_exibir) + 2, sticky='nse')
                self.alunos_grid_resizers.append(resizer)

        # Linhas de Alunos
        for row_idx, aluno in enumerate(alunos_para_exibir, start=1):
            # Coluna 0: Nome (menos espaçamento à direita para aproximar do Nível)
            name_lbl = ctk.CTkLabel(self.alunos_scroll_frame, text=aluno.get('Nome', ''), anchor="e")
            name_lbl.grid(row=row_idx, column=0, padx=(5, 2), pady=2, sticky="w")
            # Colunas seguintes: Removido o 'sticky="ew"' para permitir que as colunas encolham além da largura do texto.
            nivel_lbl = ctk.CTkLabel(self.alunos_scroll_frame, text=aluno.get('Nível', ''), anchor="center")
            nivel_lbl.grid(row=row_idx, column=1, padx=2, pady=2)
            ctk.CTkLabel(self.alunos_scroll_frame, text=str(aluno.get('Idade', '')), anchor="center").grid(row=row_idx, column=2, padx=2, pady=2)
            ctk.CTkLabel(self.alunos_scroll_frame, text=aluno.get('Categoria', ''), anchor="center").grid(row=row_idx, column=3, padx=2, pady=2)
            ctk.CTkLabel(self.alunos_scroll_frame, text=aluno.get('Turma', ''), anchor="center").grid(row=row_idx, column=4, padx=2, pady=2)
            ctk.CTkLabel(self.alunos_scroll_frame, text=aluno.get('Horário', ''), anchor="center").grid(row=row_idx, column=5, padx=2, pady=2)
            ctk.CTkLabel(self.alunos_scroll_frame, text=aluno.get('Professor', ''), anchor="center").grid(row=row_idx, column=6, padx=2, pady=2)

            # --- Coluna de Ações ---
            actions_frame = ctk.CTkFrame(self.alunos_scroll_frame, fg_color="transparent")
            actions_frame.grid(row=row_idx, column=7, padx=1, pady=0, sticky="")

            view_btn = ctk.CTkButton(actions_frame, text="ver", width=30, height=22, font=ctk.CTkFont(size=10),
                                     fg_color="transparent", border_width=1,
                                     command=lambda a=aluno: self.open_view_student_window(a))
            view_btn.grid(row=0, column=0, padx=(0, 2), pady=1, sticky="")

            edit_btn = ctk.CTkButton(actions_frame, text="editar", width=30, height=22, font=ctk.CTkFont(size=10),
                                     fg_color="transparent", border_width=1,
                                     command=lambda a=aluno: self.open_edit_student_window(a))
            edit_btn.grid(row=0, column=1, padx=(2, 0), pady=1, sticky="")

        # A lógica de auto-ajuste de 'minsize' foi removida, pois conflitava
        # com a configuração de 'weight' e causava a compressão da coluna 'Nome'.
        # A configuração de 'weight=1' para a coluna 'Nome' e 'weight=0' para as demais
        # no início desta função é suficiente para o layout desejado.

    def _sort_alunos_by(self, key):
        """Define a chave de ordenação e reconstrói a grade de alunos."""
        if self.alunos_sort_state.get('key') == key:
            # Se já está ordenando por esta chave, inverte a direção
            self.alunos_sort_state['reverse'] = not self.alunos_sort_state.get('reverse', False)
        else:
            # Nova chave de ordenação, começa com ascendente
            self.alunos_sort_state = {'key': key, 'reverse': False}
        
        self.filtrar_alunos_por_nome() # Reconstrói a grade com a nova ordenação

    def _open_filter_menu(self, key, button_widget):
        """Abre o menu de filtro para uma coluna específica."""
        # Se um menu já estiver aberto, fecha-o.
        if self.active_filter_menu and self.active_filter_menu.winfo_exists():
            # Se o clique foi no mesmo botão, o menu será fechado e a função não continuará,
            # criando o efeito de "toggle".
            is_same_button = getattr(self.active_filter_menu, 'button_widget', None) == button_widget
            self.active_filter_menu.destroy()
            if is_same_button:
                return

        # Adia a criação para garantir que o menu antigo seja destruído primeiro.
        # A verificação de segurança previne a criação se outro menu já estiver ativo.
        self.after(10, lambda: self._create_filter_menu_safely(key, button_widget))

    def _create_filter_menu_safely(self, key, button_widget):
        if not self.all_students_data or self.active_filter_menu: return

        # Coleta valores únicos da coluna
        unique_values = sorted(list(set(str(aluno.get(key, '')) for aluno in self.all_students_data if aluno.get(key) or str(aluno.get(key, '')) == '0')))

        # Cria e exibe o menu
        self.active_filter_menu = FilterMenu(self, key, unique_values, button_widget, self._apply_filter_and_sort)
        # O novo FilterMenu (Frame) se posiciona e se destrói sozinho.
        # A referência é limpa no seu próprio método destroy.

    def _apply_filter_and_sort(self, key, selected_values, sort_direction=None):
        """Callback para aplicar filtros e ordenação a partir do FilterMenu."""
        # Atualiza o estado do filtro
        if selected_values is not None:
            self.alunos_filter_state[key] = selected_values

        # Atualiza o estado da ordenação, se aplicável
        if sort_direction is not None:
            self.alunos_sort_state = {'key': key, 'reverse': sort_direction == 'desc'}

        # Reconstrói o grid
        self.filtrar_alunos_por_nome()

    def _on_filter_menu_close(self, event):
        """Limpa a referência ao menu de filtro quando ele é fechado."""
        # Garante que o evento venha do widget que estamos rastreando
        if event.widget == self.active_filter_menu:
            self.active_filter_menu = None

    def carregar_categorias(self):
        """Busca as categorias da API e as armazena em cache."""
        try:
            response = requests.get(f"{API_BASE_URL}/api/categorias")
            response.raise_for_status()
            # Ordena da maior idade mínima para a menor para facilitar a lógica de definição
            categorias = response.json()
            def _update_ui():
                # Normaliza nomes e garante que chaves esperadas existam
                sorted_cats = sorted(categorias, key=lambda x: x.get('Idade Mínima', 0), reverse=True)
                self.categorias_data = sorted_cats
            self.after(0, _update_ui)
        except requests.exceptions.RequestException as e:
            print(f"Erro ao carregar categorias: {e}")

            
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
            self.turmas_data = turmas # Armazena em cache para o formulário de add aluno

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

    # MODIFICADO: A lógica foi movida para a classe AddStudentToplevel
    def open_add_student_window(self):
        """Abre uma janela Toplevel para adicionar um novo aluno."""
        if self.add_student_toplevel is not None and self.add_student_toplevel.winfo_exists():
            self.add_student_toplevel.lift()
            return

        # Passa os dados necessários da App principal para o formulário
        form_data = {
            "turmas": self.chamada_turma_combo.cget('values'),
            "horarios": self.chamada_horario_combo.cget('values'),
            "professores": [rb.cget('text') for rb in self.chamada_prof_frame.winfo_children() if isinstance(rb, ctk.CTkRadioButton)],
            "last_data": self.last_student_add_data,
            "turmas_data": self.turmas_data,
            "categorias_data": self.categorias_data
        }
        self.add_student_toplevel = AddStudentToplevel(self, form_data, self.on_student_added)

    def open_view_student_window(self, student_data):
        """Abre uma janela Toplevel para visualizar os dados de um aluno."""
        # Fecha qualquer janela de visualização que já esteja aberta
        for w in self.winfo_children():
            if isinstance(w, ViewStudentToplevel):
                w.destroy()
        
        view_window = ViewStudentToplevel(self, student_data)
        view_window.grab_set()

    def open_edit_student_window(self, student_data):
        """Abre a janela de formulário em modo de edição."""
        if self.edit_student_toplevel is not None and self.edit_student_toplevel.winfo_exists():
            self.edit_student_toplevel.lift()
            return

        form_data = {
            "turmas": self.chamada_turma_combo.cget('values'),
            "horarios": self.chamada_horario_combo.cget('values'),
            "professores": [rb.cget('text') for rb in self.chamada_prof_frame.winfo_children() if isinstance(rb, ctk.CTkRadioButton)],
        }
        self.edit_student_toplevel = AddStudentToplevel(self, form_data, self.on_student_added, edit_data=student_data)
    def on_student_added(self, new_student_data):
        """Callback executado quando um aluno é adicionado com sucesso."""
        # 1. Salva os dados para persistência no próximo formulário
        self.last_student_add_data = {
            "turma": new_student_data["Turma"],
            "horario": new_student_data["Horário"],
            "professor": new_student_data["Professor"],
            "parQ": new_student_data["ParQ"]
        }
        # 2. Invalida o cache de alunos para forçar o recarregamento
        self.all_students_data = None
        # 3. Muda para a aba de alunos e recarrega a lista
        self.show_view("Alunos")
        # 4. Limpa a referência da janela Toplevel
        self.add_student_toplevel = None
        self.edit_student_toplevel = None


    def _center_toplevel(self, toplevel):
        toplevel.update_idletasks()
        main_x = self.winfo_x()
        main_y = self.winfo_y()
        main_w = self.winfo_width()
        main_h = self.winfo_height()
        top_w = toplevel.winfo_width()
        top_h = toplevel.winfo_height()
        x = main_x + (main_w - top_w) // 2
        y = main_y + (main_h - top_h) // 2
        toplevel.geometry(f"{top_w}x{top_h}+{x}+{y}")

    def _calcular_idade_no_ano(self, data_nasc_str):
        """Calcula a idade que o aluno fará no ano corrente."""
        if not data_nasc_str or str(data_nasc_str) == 'NaT':
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

        return None

    def _formatar_data_para_exibicao(self, data_str):
        """Formata uma string de data (vários formatos) para dd/mm/YYYY."""
        if not data_str or str(data_str) == 'NaT':
            return ""

        # Se já for um objeto datetime
        if isinstance(data_str, datetime):
            return data_str.strftime('%d/%m/%Y')

        data_text = str(data_str)
        # Tenta formatos possíveis: ISO (YYYY-mm-ddT...), YYYY-mm-dd, ou o formato já desejado
        for fmt in ('%Y-%m-%dT%H:%M:%S', '%Y-%m-%d', '%d/%m/%Y'):
            try:
                # Remove a parte da hora se existir
                parsed_date = datetime.strptime(data_text.split('T')[0], fmt.split('T')[0])
                return parsed_date.strftime('%d/%m/%Y')
            except (ValueError, TypeError):
                continue
        
        return data_text # Retorna o original se não conseguir parsear

# --- NOVA CLASSE PARA O FORMULÁRIO DE ADIÇÃO DE ALUNO ---
class AddStudentToplevel(ctk.CTkToplevel):
    def __init__(self, master, form_data, on_success_callback, edit_data=None):
        super().__init__(master)
        self.master_app = master
        self.form_data = form_data
        self.on_success = on_success_callback
        self.edit_data = edit_data
        self.is_edit_mode = edit_data is not None

        if self.is_edit_mode:
            self.title(f"Editar Aluno - {edit_data.get('Nome', '')}")
        else:
            self.title("Adicionar Novo Aluno")

        self.geometry("600x550") # Reduz a altura total da janela
        self.transient(master)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.widgets = {}
        # Carrega os dados de categorias e turmas da App principal
        self.categorias_data = self.master_app.categorias_data
        self.turmas_data = self.master_app.turmas_data

        self._build_form()

        self.after(10, lambda: self.master_app._center_toplevel(self))
        self.after(100, lambda: self.widgets['nome'].focus_set())

    def _on_close(self):
        """Libera o foco e destrói a janela, limpando a referência na aplicação principal."""
        self.grab_release()
        self.destroy()
        self.master_app.add_student_toplevel = None # Limpa a referência na app principal
        self.master_app.edit_student_toplevel = None

    def _build_form(self):
        """Constrói todos os widgets dentro do formulário."""
        # --- Frame para o formulário ---
        form_frame = ctk.CTkFrame(self, fg_color="transparent")
        form_frame.pack(pady=10, padx=20, fill="both", expand=True)
        # Configura o grid para ter 2 colunas flexíveis
        form_frame.grid_columnconfigure((0, 1), weight=1)

        # Funções de atualização
        def on_field_change(*args):
            self._update_derived_fields(self.widgets)

        # --- LINHA 1: Nome e Gênero ---
        ctk.CTkLabel(form_frame, text="Nome Completo:").grid(row=0, column=0, padx=5, pady=(5,0), sticky="w")
        self.widgets['nome'] = ctk.CTkEntry(form_frame, 
                                            placeholder_text="Nome do aluno",
                                            width=350, height=30)
        self.widgets['nome'].grid(row=1, column=0, padx=5, pady=(0, 10), sticky="ew")

        ctk.CTkLabel(form_frame, text="Gênero:").grid(row=0, column=1, padx=5, pady=(5,0), sticky="w")
        self.widgets['genero'] = ctk.CTkComboBox(form_frame, 
                                                 values=["Feminino", "Masculino", "Não Binário"],
                                                 width=120, height=30)
        self.widgets['genero'].grid(row=1, column=1, padx=5, pady=(0, 10), sticky="ew")        
        self.widgets['genero'].set("")

        # --- LINHA 2: Aniversário e Whatsapp ---
        ctk.CTkLabel(form_frame, text="Aniversário:").grid(row=2, column=0, padx=5, pady=(5,0), sticky="w")
        self.widgets['data_nasc'] = ctk.CTkEntry(form_frame, 
                                                 placeholder_text="dd/mm/aaaa",
                                                 width=120, height=30)
        self.widgets['data_nasc'].grid(row=3, column=0, padx=5, pady=(0, 10), sticky="ew")
        self.widgets['data_nasc'].bind("<KeyRelease>", lambda e, w=self.widgets['data_nasc']: self._format_date_entry(e, w))
        self.widgets['data_nasc'].bind("<FocusOut>", lambda e: on_field_change())

        ctk.CTkLabel(form_frame, text="Whatsapp:").grid(row=2, column=1, padx=5, pady=(5,0), sticky="w")
        self.widgets['telefone'] = ctk.CTkEntry(form_frame,
                                                width=180, height=30)
        self.widgets['telefone'].grid(row=3, column=1, padx=5, pady=(0, 10), sticky="ew")
        self.widgets['telefone'].bind("<KeyRelease>", self._format_phone_entry)

        # --- LINHA 3: Turma e Horário ---
        ctk.CTkLabel(form_frame, text="Turma:").grid(row=4, column=0, padx=5, pady=(5,0), sticky="w")
        self.widgets['turma'] = ctk.CTkComboBox(form_frame, 
                                                values=self.form_data.get('turmas', []), 
                                                command=on_field_change,
                                                width=120, height=30)
        self.widgets['turma'].grid(row=5, column=0, padx=5, pady=(0, 10), sticky="ew")        
        # Se não estiver em modo de edição, usa os últimos dados. Senão, usa os dados do aluno.
        last_turma = self.form_data.get('last_data', {}).get("turma", "")
        self.widgets['turma'].set(self.form_data.get('last_data', {}).get("turma", ""))

        ctk.CTkLabel(form_frame, text="Horário:").grid(row=4, column=1, padx=5, pady=(5,0), sticky="w")
        self.widgets['horario'] = ctk.CTkComboBox(form_frame, 
                                                  values=self.form_data.get('horarios', []), 
                                                  command=on_field_change,
                                                  width=120, height=30)
        self.widgets['horario'].grid(row=5, column=1, padx=5, pady=(0, 10), sticky="ew")        
        last_horario = self.form_data.get('last_data', {}).get("horario", "")
        self.widgets['horario'].set(self.form_data.get('last_data', {}).get("horario", ""))

        # --- LINHA 4: Professor e ParQ ---
        # Frame para Professor
        prof_container = ctk.CTkFrame(form_frame, fg_color="transparent")
        prof_container.grid(row=6, column=0, columnspan=2, padx=0, pady=0, sticky="ew")
        
        last_prof = self.form_data.get('last_data', {}).get("professor", "")
        ctk.CTkLabel(prof_container, text="Professor:").pack(anchor="w", padx=5)
        self.widgets['prof_var'] = tk.StringVar(value=self.form_data.get('last_data', {}).get("professor", ""))
        self.widgets['prof_var'].trace_add("write", on_field_change) # Garante que a mudança de professor atualize os campos
        prof_frame = ctk.CTkFrame(prof_container, fg_color="transparent")
        prof_frame.pack(fill="x", padx=5, pady=(0, 10), anchor="w")
        for i, prof in enumerate(self.form_data.get('professores', [])):
            ctk.CTkRadioButton(prof_frame, text=prof, variable=self.widgets['prof_var'], value=prof).pack(side="left", padx=(0, 15))

        # Frame para ParQ
        parq_container = ctk.CTkFrame(form_frame, fg_color="transparent")
        parq_container.grid(row=7, column=0, columnspan=2, padx=0, pady=0, sticky="ew")
        ctk.CTkLabel(parq_container, text="ParQ Assinado:").pack(anchor="w", padx=5)
        last_parq = self.form_data.get('last_data', {}).get("parQ", "Sim")
        self.widgets['parq_var'] = tk.StringVar(value=last_parq)
        parq_frame = ctk.CTkFrame(parq_container, fg_color="transparent")
        parq_frame.pack(fill="x", padx=5, pady=(0, 10), anchor="w")
        ctk.CTkRadioButton(parq_frame, text="Sim", variable=self.widgets['parq_var'], value="Sim").pack(side="left", padx=(0, 15))
        ctk.CTkRadioButton(parq_frame, text="Não", variable=self.widgets['parq_var'], value="Não").pack(side="left")

        # --- Labels de Preenchimento Automático ---
        auto_frame = ctk.CTkFrame(form_frame, fg_color="transparent")
        auto_frame.grid(row=8, column=0, columnspan=2, sticky="ew", padx=5, pady=15)
        auto_frame.grid_columnconfigure((0, 1, 2), weight=1) # 3 colunas flexíveis dentro deste frame

        ctk.CTkLabel(auto_frame, text="Idade (no ano):").grid(row=0, column=0, sticky="w")
        self.widgets['idade_label'] = ctk.CTkLabel(auto_frame, text="-", font=ctk.CTkFont(weight="bold"))
        self.widgets['idade_label'].grid(row=1, column=0, sticky="w", pady=(0,5))

        ctk.CTkLabel(auto_frame, text="Categoria:").grid(row=0, column=1, sticky="w")
        self.widgets['categoria_label'] = ctk.CTkLabel(auto_frame, text="-", font=ctk.CTkFont(weight="bold"))
        self.widgets['categoria_label'].grid(row=1, column=1, sticky="w", pady=(0,5))

        ctk.CTkLabel(auto_frame, text="Nível:").grid(row=0, column=2, sticky="w")
        self.widgets['nivel_label'] = ctk.CTkLabel(auto_frame, text="-", font=ctk.CTkFont(weight="bold"))
        self.widgets['nivel_label'].grid(row=1, column=2, sticky="w", pady=(0,5))

        # --- Frame para os botões de ação ---
        button_frame = ctk.CTkFrame(form_frame, fg_color="transparent")
        button_frame.grid(row=9, column=0, columnspan=2, pady=(10, 4), padx=20, sticky="ew") # Reduz o espaçamento inferior
        button_frame.grid_columnconfigure((0, 1), weight=1)
        
        # --- Botão Cancelar ---
        cancel_text = "Limpar" if not self.is_edit_mode else "Cancelar"
        cancel_command = self._clear_personal_info_fields if not self.is_edit_mode else self._on_close
        cancel_button = ctk.CTkButton(button_frame, text=cancel_text, command=cancel_command,
                                      fg_color="transparent", border_width=1,
                                      height=40)
        cancel_button.grid(row=0, column=0, padx=(0, 5), sticky="ew")
        # --- Botão Adicionar/Salvar ---
        add_text = "Adicionar Aluno" if not self.is_edit_mode else "Salvar Alterações"
        add_button = ctk.CTkButton(button_frame, text=add_text, command=self._submit, height=40)
        add_button.grid(row=0, column=1, padx=(5, 0), sticky="ew")

        if self.is_edit_mode:
            self._populate_form_for_edit()

        # Navegação com Enter
        self._set_enter_navigation()
        on_field_change() # Inicializa os campos derivados

    def _populate_form_for_edit(self):
        """Preenche o formulário com os dados do aluno para edição."""
        if not self.edit_data:
            return

        self.widgets['nome'].insert(0, self.edit_data.get('Nome', ''))
        self.widgets['genero'].set(self.edit_data.get('Gênero', ''))

        # Formata a data de nascimento para dd/mm/YYYY
        data_nasc_str = self.edit_data.get('Aniversario') # Já foi normalizado
        if data_nasc_str:
            self.widgets['data_nasc'].insert(0, self.master_app._formatar_data_para_exibicao(str(data_nasc_str)))

        self.widgets['telefone'].insert(0, self.edit_data.get('Whatsapp', '')) # Já foi normalizado
        self.widgets['turma'].set(self.edit_data.get('Turma', ''))
        self.widgets['horario'].set(self.edit_data.get('Horário', ''))
        self.widgets['prof_var'].set(self.edit_data.get('Professor', ''))
        self.widgets['parq_var'].set(self.edit_data.get('ParQ', 'Sim'))

    def _set_enter_navigation(self):
        """Configura a tecla Enter para pular para o próximo widget."""
        widgets_order = [
            self.widgets['nome'], self.widgets['data_nasc'], self.widgets['genero'],
            self.widgets['telefone'], self.widgets['turma'], self.widgets['horario']
        ]
        for i, widget in enumerate(widgets_order):
            next_widget = widgets_order[i + 1] if i + 1 < len(widgets_order) else None
            if next_widget:
                widget.bind("<Return>", lambda e, w=next_widget: w.focus_set())

    def _clear_personal_info_fields(self):
        """Limpa apenas os campos de informação pessoal do aluno e foca no nome."""
        # Limpa os campos de texto (Entry)
        self.widgets['nome'].delete(0, "end")
        self.widgets['data_nasc'].delete(0, "end")
        self.widgets['telefone'].delete(0, "end")

        # Limpa os ComboBoxes
        self.widgets['genero'].set("")
        
        # Coloca o cursor de volta no campo "Nome"
        self.widgets['nome'].focus_set()

    def _submit(self):
        # Coleta os dados
        data = {
            "Nome": self.widgets['nome'].get(),
            "Aniversario": self.widgets['data_nasc'].get(),
            "Gênero": self.widgets['genero'].get(),
            "Whatsapp": self.widgets['telefone'].get(), # Envia como 'Whatsapp' para consistência
            "Turma": self.widgets['turma'].get(),
            "Horário": self.widgets['horario'].get(),
            "Professor": self.widgets['prof_var'].get(),
            "ParQ": self.widgets['parq_var'].get(),
            "Nível": self.widgets['nivel_label'].cget("text"),
            "Categoria": self.widgets['categoria_label'].cget("text")
        }

        # Validação
        if not all([data["Nome"], data["Aniversario"], data["Turma"], data["Horário"], data["Professor"]]):
            messagebox.showerror("Erro", "Por favor, preencha todos os campos obrigatórios (Nome, Data, Turma, Horário, Professor).", parent=self)
            return

        # Envia para a API
        try:
            if self.is_edit_mode:
                # Endpoint para ATUALIZAR um aluno existente
                aluno_id = self.edit_data.get('id') # Supondo que a API retorna um 'id'
                if not aluno_id:
                    messagebox.showerror("Erro", "ID do aluno não encontrado. Não é possível salvar.", parent=self)
                    return
                response = requests.put(f"{API_BASE_URL}/api/aluno/{aluno_id}", json=data)
                success_message = f"Dados de '{data['Nome']}' salvos com sucesso!"
            else:
                # Endpoint para CRIAR um novo aluno
                response = requests.post(f"{API_BASE_URL}/api/aluno", json=data)
                success_message = f"Aluno '{data['Nome']}' adicionado com sucesso!"

            response.raise_for_status()
            
            messagebox.showinfo("Sucesso", success_message, parent=self)

            # Chama o callback de sucesso na classe App
            if self.on_success:
                self.on_success(data)
            
            if self.is_edit_mode:
                self._on_close() # Fecha a janela após salvar
            else:
                # Limpa os campos pessoais para a próxima adição, mantendo os da turma
                self._clear_personal_info_fields()
            
        except requests.exceptions.RequestException as e:
            action = "salvar as alterações" if self.is_edit_mode else "adicionar o aluno"
            error_msg = f"Não foi possível {action}.\n\nErro: {e}"
            try:
                error_detail = e.response.json().get('detail', 'Erro desconhecido do servidor.')
                error_msg += f"\nDetalhe: {error_detail}"
            except:
                pass
            messagebox.showerror("Erro de API", error_msg, parent=self)

    def _format_date_entry(self, event, entry_widget):
        # Ignora teclas de controle que não modificam o texto
        if event.keysym not in ("BackSpace", "Delete") and len(event.char) == 0:
            return

        cursor_pos = entry_widget.index(tk.INSERT)
        text = entry_widget.get()
        numeros = "".join(filter(str.isdigit, text))
        
        if event.keysym == "BackSpace":
            # Lógica para ajustar o cursor ao apagar perto de um "/"
            if cursor_pos > 0 and text[cursor_pos - 1] == '/':
                cursor_pos -= 1

        formatted = ""
        old_len = len(text)

        if len(numeros) > 0: formatted = numeros[:2]
        if len(numeros) > 2: formatted += "/" + numeros[2:4]
        if len(numeros) > 4: formatted += "/" + numeros[4:8]
        
        entry_widget.delete(0, "end")
        entry_widget.insert(0, formatted)

        # Restaura a posição do cursor, ajustando para a adição/remoção de barras
        new_len = len(formatted)
        cursor_delta = new_len - old_len
        new_cursor_pos = cursor_pos + cursor_delta if cursor_delta > 0 else cursor_pos
        entry_widget.icursor(min(new_cursor_pos, new_len))

    def _format_phone_entry(self, event):
        """Formata o número de telefone no formato (##) # ####-#### enquanto o usuário digita."""
        # Ignora teclas de controle (exceto Backspace, que é tratado pela remoção de não-dígitos)
        if event.keysym not in ("BackSpace", "Delete") and len(event.char) == 0:
            return

        entry_widget = event.widget
        # Salva a posição do cursor e o texto ANTES de qualquer modificação
        cursor_pos = entry_widget.index(tk.INSERT)
        text = entry_widget.get()
        old_len = len(text)

        numeros = "".join(filter(str.isdigit, text))
        numeros = numeros[:11]

        formatted = ""
        if len(numeros) > 0:
            formatted = f"({numeros[:2]}"
        if len(numeros) > 2:
            # Adiciona o nono dígito
            formatted = f"({numeros[:2]}) {numeros[2:3]}"
        if len(numeros) > 3:
            # Adiciona os 4 dígitos seguintes
            formatted = f"({numeros[:2]}) {numeros[2:3]} {numeros[3:7]}"
        if len(numeros) > 7:
            # Adiciona o hífen e os 4 dígitos finais
            formatted = f"({numeros[:2]}) {numeros[2:3]} {numeros[3:7]}-{numeros[7:11]}"
        
        entry_widget.delete(0, "end")
        entry_widget.insert(0, formatted)

        # Restaura a posição do cursor, ajustando para a adição de caracteres de formatação
        new_len = len(formatted)
        entry_widget.icursor(min(new_len, cursor_pos + (new_len - old_len)))

    # MODIFICADO: Agora usa os dados de turmas e categorias da App
    def _update_derived_fields(self, widgets):
        # 1. Calcular Idade e Categoria
        idade = self.master_app._calcular_idade_no_ano(widgets['data_nasc'].get())
        categoria = self._definir_categoria(idade)
        if idade is not None:
            widgets['idade_label'].configure(text=str(idade))
        else:
            widgets['idade_label'].configure(text="-")
        widgets['categoria_label'].configure(text=categoria)

        # 2. Encontrar Nível
        nivel = self._encontrar_nivel_da_turma(widgets)
        widgets['nivel_label'].configure(text=nivel)

    def _definir_categoria(self, idade):
        """Define a categoria do aluno com base na idade e nos dados de categoria em cache."""
        categorias_data = self.categorias_data
        if idade is None or not categorias_data:
            return 'Não Categorizado'
        
        # Garante que a lista esteja ordenada da maior idade mínima para a menor.
        # Isso torna a lógica de busca segura, mesmo que os dados da API não venham ordenados.
        categorias_ordenadas = sorted(categorias_data, key=lambda x: x.get('Idade Mínima', 0), reverse=True)

        categoria_adequada = 'Não Categorizado'
        for cat in categorias_ordenadas:
            if idade >= cat.get('Idade Mínima', 0):
                categoria_adequada = cat.get('Nome da Categoria') or cat.get('Categoria') or categoria_adequada
                # Uma vez que a primeira correspondência é encontrada (devido à ordenação), podemos parar.
                break
        return categoria_adequada

    def _encontrar_nivel_da_turma(self, widgets):
        """Busca o nível correspondente com base na turma, horário e professor selecionados."""
        turma = widgets['turma'].get()
        horario = widgets['horario'].get()
        prof = widgets['prof_var'].get()
        turmas_data = self.turmas_data

        if all([turma, horario, prof, turmas_data]):
            for t_info in turmas_data:
                if (t_info.get("Turma") == turma and t_info.get("Horário") == horario and t_info.get("Professor") == prof):
                    return t_info.get("Nível", "-")
        return "-"

# --- NOVA CLASSE PARA VISUALIZAÇÃO DE ALUNO ---
class ViewStudentToplevel(ctk.CTkToplevel):
    def __init__(self, master, student_data):
        super().__init__(master)
        self.master_app = master
        self.student_data = student_data

        self.title(f"Detalhes de {student_data.get('Nome', 'Aluno')}")
        self.geometry("450x400")
        self.transient(master)
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        self._build_view()
        self.after(10, lambda: self.master_app._center_toplevel(self))

    def _build_view(self):
        main_frame = ctk.CTkFrame(self, fg_color="transparent")
        main_frame.pack(pady=15, padx=20, fill="both", expand=True)
        main_frame.grid_columnconfigure(1, weight=1)

        # Mapeamento de chaves de dados para labels de exibição
        fields = {
            "Nome": "Nome:", "Gênero": "Gênero:", "Aniversario": "Aniversário:",
            "Whatsapp": "Whatsapp:", "Turma": "Turma:", "Horário": "Horário:",
            "Professor": "Professor:", "Nível": "Nível:", "Idade": "Idade (no ano):",
            "Categoria": "Categoria:", "ParQ": "ParQ Assinado:"
        }

        row = 0
        for key, label_text in fields.items():
            # Obtém o valor da chave padronizada. A normalização já foi feita.
            value = self.student_data.get(key)
            if key == "Aniversario":
                value = self.master_app._formatar_data_para_exibicao(value)

            ctk.CTkLabel(main_frame, text=label_text, anchor="e", font=ctk.CTkFont(weight="bold")).grid(row=row, column=0, padx=(0, 10), pady=4, sticky="ew")
            ctk.CTkLabel(main_frame, text=str(value if value is not None else "-"), anchor="w").grid(row=row, column=1, padx=0, pady=4, sticky="ew")
            row += 1

        ctk.CTkButton(main_frame, text="Fechar", command=self.destroy).grid(row=row, column=0, columnspan=2, pady=(20, 0), padx=50, sticky="ew")

class MenuResizer(ctk.CTkFrame):
    """Um widget que permite redimensionar a largura de seu widget mestre (o menu) a partir da esquerda ou direita."""
    def __init__(self, master, side="right"):
        super().__init__(master, width=7, cursor="sb_h_double_arrow", fg_color="transparent")
        self.master_menu = master
        self.side = side
        self._start_x = 0
        self._start_width = 0
        self._start_menu_x = 0

        self.bind("<Button-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)

    def _on_press(self, event):
        """Captura a posição inicial do mouse e a largura atual do menu."""
        self._start_x = event.x_root
        self._start_width = self.master_menu.winfo_width()
        self._start_menu_x = self.master_menu.winfo_x()

    def _on_drag(self, event):
        """Calcula a nova largura com base no movimento do mouse e redimensiona o menu."""
        # Verifica se o modo de edição está ativo na aplicação principal
        if not self.master_menu.master_app.alunos_grid_edit_mode.get():
            return

        delta_x = event.x_root - self._start_x
        min_width = 20 # Largura mínima para evitar que o menu desapareça

        if self.side == "right":
            new_width = max(min_width, self._start_width + delta_x)
            self.master_menu.configure(width=new_width)
        elif self.side == "left":
            # Ao arrastar para a esquerda, a largura aumenta e a posição X diminui
            new_width = max(min_width, self._start_width - delta_x)
            new_x = self._start_menu_x + delta_x
            self.master_menu.configure(width=new_width)
            self.master_menu.place_configure(x=new_x) # Reposiciona o menu


# --- CLASSE PARA O MENU DE FILTRO ESTILO EXCEL ---
class FilterMenu(ctk.CTkFrame):
    # --- CONFIGURAÇÃO DE ALTURA ---
    # Defina um número (ex: 400) para uma altura fixa ou None para ajuste automático à janela.
    MANUAL_HEIGHT = 280

    def __init__(self, master, key, values, button_widget, callback):
        # O master agora é a janela principal da aplicação (App).
        # A altura será definida depois que o conteúdo for criado.
        super().__init__(master, corner_radius=8, border_width=1)

        self.key = key
        self.callback = callback
        self.button_widget = button_widget # Armazena o botão que abriu o menu
        self.master_app = master

        # --- Variáveis de estado ---
        # Se não houver filtro ativo para a chave, todos os valores são selecionados por padrão.
        active_filters = self.master_app.alunos_filter_state.get(self.key)
        initial_state = {value: tk.BooleanVar(value=True) for value in values} if active_filters is None else \
                        {value: tk.BooleanVar(value=value in active_filters) for value in values}
        self.check_vars = initial_state

        # Define um padding horizontal menor para todos os frames internos
        inner_padx = 3

        # --- Botões de Ordenação ---
        sort_frame = ctk.CTkFrame(self, fg_color="transparent")
        sort_frame.pack(fill="x", padx=inner_padx, pady=(5, 2))        
        
        # Define os textos dos botões de ordenação com base na coluna
        if self.key in ['Nome', 'Turma', 'Professor']:
            asc_text, desc_text = "Ordenar A-Z", "Ordenar Z-A"
        elif self.key in ['Idade', 'Horário']:
            asc_text, desc_text = "Ordenar < para >", "Ordenar > para <"
        elif self.key in ['Nível', 'Categoria']:
            asc_text, desc_text = "Ordenar < para >", "Ordenar > para <"
        else:
            asc_text, desc_text = "Ordenar Crescente", "Ordenar Decrescente"

        ctk.CTkButton(sort_frame, 
                      text=asc_text, 
                      height=22, 
                      font=ctk.CTkFont(size=9), 
                      anchor="center",
                      command=lambda: self._apply_and_close(sort_direction='asc')).pack(fill="x")
        ctk.CTkButton(sort_frame, 
                      text=desc_text, 
                      height=22, 
                      font=ctk.CTkFont(size=9), 
                      anchor="center",
                      command=lambda: self._apply_and_close(sort_direction='desc')).pack(fill="x", pady=(2,0))
        
        # --- Linha divisória ---
        ctk.CTkFrame(self, height=1, fg_color="gray50").pack(fill="x", padx=inner_padx, pady=3)

        # --- Filtros ---
        filter_frame = ctk.CTkFrame(self, fg_color="transparent")
        filter_frame.pack(fill="x", padx=inner_padx)
        ctk.CTkButton(filter_frame, text="Limpar Filtro", height=24, font=ctk.CTkFont(size=9), command=self._clear_filters).pack(fill="x")

        # --- Posicionamento e Cálculo de Altura (FEITO ANTES DE CRIAR O SCROLL FRAME) ---
        # Primeiro, calcula a posição e tamanho padrão
        self.update_idletasks()
        default_width = max(200, button_widget.winfo_width())
        button_x_rel = button_widget.winfo_rootx() - master.winfo_rootx()
        default_y = button_widget.winfo_rooty() - master.winfo_rooty() + button_widget.winfo_height()
        default_x = button_x_rel + 5

        # Verifica se há geometria em cache para esta coluna e a utiliza
        cached_geometry = self.master_app.filter_menu_geometry_cache.get(self.key)
        initial_width = cached_geometry.get('width', default_width) if cached_geometry else default_width
        x = cached_geometry.get('x', default_x) if cached_geometry else default_x
        y = cached_geometry.get('y', default_y) if cached_geometry else default_y

        if self.MANUAL_HEIGHT is not None:
            menu_height = self.MANUAL_HEIGHT
        else:
            # Calcula a altura máxima permitida para o menu não sair da tela
            menu_height = master.winfo_height() - default_y - 15 # Usa o Y padrão para o cálculo de altura máxima
        
        self.configure(width=initial_width, height=menu_height)
        self.pack_propagate(False)

        # --- Scrollable Frame para os checkboxes ---
        # O frame se expandirá para preencher o espaço vertical disponível.
        scroll_frame = ctk.CTkScrollableFrame(self, label_text="Valores", label_font=ctk.CTkFont(size=9))
        scroll_frame.pack(expand=True, fill="both", padx=inner_padx, pady=3)


        # Checkbox "(Selecionar Tudo)"
        # Se o filtro para esta chave não existir, todos são selecionados por padrão.
        self.select_all_var = tk.BooleanVar(value=False) # Será definido abaixo
        ctk.CTkCheckBox(scroll_frame, text="(Tudo)", variable=self.select_all_var, 
                        font=ctk.CTkFont(size=9),
                        command=lambda: self._toggle_all(self.select_all_var.get())).pack(anchor="w", padx=1)

        for value in values:
            ctk.CTkCheckBox(scroll_frame, text=value, variable=self.check_vars[value], 
                            font=ctk.CTkFont(size=11),
                            command=self._apply_filters_live).pack(anchor="w", padx=1)

        self._update_select_all_checkbox() # Atualiza o estado inicial do checkbox "Tudo"
        
        # --- Botões de Ação ---
        action_frame = ctk.CTkFrame(self, fg_color="transparent")
        action_frame.pack(fill="x", padx=inner_padx, pady=(4, 4))
        action_frame.grid_columnconfigure((0,1), weight=1)
        ctk.CTkButton(action_frame, text="OK", height=24, font=ctk.CTkFont(size=10), command=self._apply_and_close).grid(row=0, column=0, sticky="ew", padx=(0,1))
        ctk.CTkButton(action_frame, text="Cancela", height=24, font=ctk.CTkFont(size=10), fg_color="transparent", 
                      border_width=1, command=self.destroy).grid(row=0, column=1, sticky="ew", padx=(1,0))


        # Posiciona o menu
        self.place(x=x, y=y)
        self.lift()

        # Adiciona os "puxadores" de redimensionamento apenas se o modo de edição estiver ativo
        if self.master_app.alunos_grid_edit_mode.get():
            right_resizer = MenuResizer(self, side="right")
            right_resizer.place(relx=1.0, rely=0, relheight=1.0, anchor="ne")

            left_resizer = MenuResizer(self, side="left")
            left_resizer.place(relx=0.0, rely=0, relheight=1.0, anchor="nw")

        # Fecha o menu se o usuário clicar fora dele
        self.master_app.bind("<Button-1>", self._on_click_outside, add="+")

    def _toggle_all(self, select_state):
        """Seleciona ou deseleciona todos os checkboxes."""
        for var in self.check_vars.values():
            var.set(select_state)
        self._apply_filters_live()

    def _update_select_all_checkbox(self):
        """Atualiza o estado do checkbox 'Selecionar Tudo' com base nos outros."""
        all_selected = all(var.get() for var in self.check_vars.values())
        self.select_all_var.set(all_selected)

    def _apply_filters_live(self):
        """Aplica os filtros selecionados sem fechar o menu e atualiza o checkbox 'Tudo'."""
        self._update_select_all_checkbox()
        selected_values = {value for value, var in self.check_vars.items() if var.get()}
        self.callback(self.key, selected_values, sort_direction=None) # Não altera a ordenação

    def _clear_filters(self):
        """Limpa o filtro para esta chave e fecha."""
        # Passa um conjunto vazio para limpar o filtro e None para a ordenação,
        # indicando que a ordenação também deve ser resetada se for desta coluna.
        # A lógica no callback principal cuidará de remover a chave do estado de ordenação.
        self.callback(self.key, set(), sort_direction=None)
        self.destroy()

    def _apply_and_close(self, sort_direction=None):
        """Aplica os filtros selecionados e/ou ordenação e fecha a janela."""
        selected_values = {value for value, var in self.check_vars.items() if var.get()}
        self.callback(self.key, selected_values, sort_direction)
        self.destroy()

    def _on_click_outside(self, event):
        """Verifica se o clique foi fora do menu e o fecha."""
        # Identifica o widget que foi clicado nas coordenadas do evento.
        clicked_widget = self.winfo_containing(event.x_root, event.y_root)

        # Percorre a hierarquia de widgets a partir do widget clicado.
        # Se o menu (self) for encontrado como um "pai" na hierarquia,
        # significa que o clique foi dentro do menu.
        widget = clicked_widget
        while widget:
            if widget == self:
                return # O clique foi interno, então não faz nada.
            widget = widget.master
        self.destroy() # Se o loop terminar, o clique foi externo, então fecha o menu.

    def destroy(self):
        """Sobrescreve o método destroy para limpar referências."""
        # Salva a geometria apenas se o modo de edição estiver ativo
        if self.master_app.alunos_grid_edit_mode.get():
            if self.winfo_exists(): # Garante que a janela ainda existe ao obter a geometria
                self.master_app.filter_menu_geometry_cache[self.key] = {
                    'width': self.winfo_width(),
                    'x': self.winfo_x(),
                    'y': self.winfo_y()
                }

        if self.master_app.active_filter_menu == self:
            self.master_app.active_filter_menu = None
        self.master_app.unbind("<Button-1>") # Remove o bind para não acumular
        super().destroy()

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
