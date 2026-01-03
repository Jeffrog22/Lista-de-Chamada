import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox
import json
from tkinter import font as tkfont
import requests
import threading
from datetime import datetime
from urllib.parse import quote
import webbrowser
import calendar

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
        self.sidebar_frame.grid_rowconfigure(0, weight=1) # Permite que os frames internos expandam

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
        
        # Botão Exclusões (sem ação definida por enquanto)
        self.btn_exclusoes_main = ctk.CTkButton(self.main_menu_frame, text="Exclusões", command=lambda: self.show_view("Exclusões"), fg_color="transparent", border_width=1)
        self.btn_exclusoes_main.grid(row=4, column=0, padx=20, pady=(20, 20), sticky="s")
            
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
        
        self.chamada_exclusoes_button = ctk.CTkButton(self.chamada_control_frame, text="Exclusões", command=lambda: self.show_view("Exclusões"), fg_color="transparent", border_width=1)
        self.chamada_exclusoes_button.grid(row=8, column=0, columnspan=2, padx=20, pady=(0, 20), sticky="s")

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
        self.tab_view.add("Exclusões")
        self.tab_view.set("Chamada") 

        # --- Botão Adicionar Aluno (canto superior direito, sobreposto) ---
        # Movido para ser filho da janela principal (self) para não ser coberto pelo tab_view
        self.add_student_button = ctk.CTkButton(self, text="+ Adicionar Aluno", command=self.open_add_student_window)
        self.add_student_button.place(relx=1.0, rely=0.0, x=-20, y=10, anchor="ne")

        # --- Botão Adicionar Turma (canto superior esquerdo, visível apenas na aba Turmas) ---
        self.add_turma_button = ctk.CTkButton(self, text="+ Adicionar Turma", command=self.open_add_turma_window)
        # Inicialmente oculto, gerenciado por show_view

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

        # --- 2.5. Conteúdo da Aba "Exclusões" ---
        self.tab_view.tab("Exclusões").grid_columnconfigure(0, weight=1)
        self.tab_view.tab("Exclusões").grid_rowconfigure(0, weight=1)
        self.exclusoes_scroll_frame = ctk.CTkScrollableFrame(self.tab_view.tab("Exclusões"), label_text="Histórico de Exclusões")
        self.exclusoes_scroll_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        # --- ARMAZENAMENTO DE ESTADO ---
        self.sidebar_is_open = True
        meses = [datetime(2000, i, 1).strftime('%B') for i in range(1, 13)]
        self.alunos_sort_state = [] # Lista de dicionários para histórico de ordenação: [{'key': 'Nome', 'reverse': False}, ...]
        self.chamada_sort_reverse = False # Controle de ordenação da chamada
        self.alunos_filter_state = {} # Para filtros por coluna
        self.chamada_data = {} # Guarda os dados da API
        self.turmas_filter_state = {} # Estado dos filtros da aba Turmas
        self.turmas_sort_state = [] # Estado da ordenação da aba Turmas
        self.chamada_widgets = {} # Guarda os widgets de botão para poder ler o estado
        self.all_students_data = None # Cache para todos os alunos
        self.categorias_data = None # Cache para as categorias
        self.turmas_data = None # Cache para os dados das turmas (usado para encontrar o nível)
        self.active_filter_menu = None # Referência ao menu de filtro ativo
        self.add_student_toplevel = None # Referência para a janela de adicionar aluno
        self.edit_student_toplevel = None # Referência para a janela de editar aluno
        self.add_turma_toplevel = None # Referência para a janela de adicionar turma
        self.filter_menu_geometry_cache = {} # Cache para a geometria dos menus de filtro
        self.column_widths_cache = {} # Cache para a largura das colunas da aba Alunos
        self.last_student_add_data = {} # Guarda os últimos dados para preenchimento
        self.alunos_grid_resizers = [] # Lista para guardar os widgets de redimensionamento
        self.window_geometries = {} # Cache para geometria das janelas (Toplevels)
        self.chamada_undo_stack = [] # Pilha para desfazer ações na chamada
        
        # Mapeamento de views para seus frames de controle
        self.control_frames = {
            "Chamada": self.chamada_control_frame,
        }

        # --- INICIALIZAÇÃO ---
        self.carregar_filtros_iniciais()
        self._load_config() # Carrega as configurações salvas
        self.carregar_lista_turmas() # Carrega dados de turmas (agora gerencia sua própria thread)
        self.run_in_thread(self.carregar_categorias) # Carrega categorias em background na inicialização
        self.show_main_menu() # Garante que o menu principal seja exibido no início

    def _load_config(self):
        """Carrega configurações do app de um arquivo JSON."""
        try:
            with open("config.json", "r") as f:
                config = json.load(f)
                self.column_widths_cache = config.get("column_widths", {})

                # --- CORREÇÃO: Validação da geometria do menu ao carregar ---
                # Ignora geometrias salvas que são inválidas (ex: largura < 50)
                # Isso impede que um menu "quebrado" seja carregado.
                loaded_geometries = config.get("filter_menu_geometry", {})
                self.filter_menu_geometry_cache = {
                    key: geo for key, geo in loaded_geometries.items()
                    if geo.get('width', 0) > 50
                }
                self.window_geometries = config.get("window_geometries", {})
        except (FileNotFoundError, json.JSONDecodeError):
            self.column_widths_cache = {} # Se o arquivo não existe ou está corrompido, usa o padrão
            self.filter_menu_geometry_cache = {}

    def _save_config(self):
        """Salva as configurações atuais do app em um arquivo JSON."""
        # 1. Carrega a configuração existente para não sobrescrever dados não relacionados.
        try:
            with open("config.json", "r") as f:
                config = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            config = {}

        # 2. Atualiza a largura das colunas da aba Alunos (apenas se em modo de edição para segurança)
        if self.alunos_grid_edit_mode.get() and self.alunos_scroll_frame.winfo_exists():
            headers = ['Nome', 'Nível', 'Idade', 'Categoria', 'Turma', 'Horário', 'Professor', '']
            current_widths = {headers[i]: self.alunos_scroll_frame.grid_columnconfigure(i)['minsize'] for i in range(len(headers))}
            config["column_widths"] = current_widths
            self.column_widths_cache = current_widths
        else:
            config["column_widths"] = self.column_widths_cache

        # 3. Atualiza a geometria dos menus de filtro no dicionário de config
        # Se houver um menu aberto, salva sua geometria atual no cache antes de escrever no arquivo
        if self.alunos_grid_edit_mode.get() and self.active_filter_menu and self.active_filter_menu.winfo_exists():
            if self.active_filter_menu.winfo_height() > 50:
                self.filter_menu_geometry_cache[self.active_filter_menu.key] = {
                    'width': self.active_filter_menu.winfo_width(),
                    'x': self.active_filter_menu.winfo_x(),
                    'y': self.active_filter_menu.winfo_y()
                }

        config["filter_menu_geometry"] = self.filter_menu_geometry_cache

        # 4. Salva geometrias das janelas abertas (se houver)
        if self.add_turma_toplevel and self.add_turma_toplevel.winfo_exists():
            self.window_geometries["add_turma"] = self.add_turma_toplevel.geometry()
        if self.add_student_toplevel and self.add_student_toplevel.winfo_exists():
            self.window_geometries["add_student"] = self.add_student_toplevel.geometry()
        if self.edit_student_toplevel and self.edit_student_toplevel.winfo_exists():
            self.window_geometries["add_student"] = self.edit_student_toplevel.geometry()
            
        config["window_geometries"] = self.window_geometries

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

        # Esconde o botão de adicionar turma por padrão
        self.add_turma_button.place_forget()

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
            # Mostra o botão de adicionar turma (posicionado à direita do menu hambúrguer)
            self.add_turma_button.place(relx=0.0, rely=0.0, x=70, y=10, anchor="nw")
        elif view_name == "Exclusões":
            self.carregar_lista_exclusoes()
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
            
            # Recalcula as datas da chamada com base nos dias da semana da turma e no mês atual
            # Isso garante que novas turmas (ou turmas sem registros) mostrem as colunas corretas
            dias_calculados = self._calcular_dias_chamada(self.chamada_turma_combo.get())
            if dias_calculados:
                self.chamada_data['datas'] = dias_calculados

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

    def _calcular_dias_chamada(self, turma_str):
        """Gera lista de datas (dd/mm/yyyy) do mês atual para os dias da semana da turma."""
        if not turma_str:
            return []
            
        turma_lower = turma_str.lower()
        # Mapeia dias da semana (0=Segunda, 6=Domingo)
        dias_map = {
            "segunda": 0, "terça": 1, "terca": 1, 
            "quarta": 2, "quinta": 3, "sexta": 4, 
            "sábado": 5, "sabado": 5, "domingo": 6
        }
        
        dias_indices = set()
        for nome, idx in dias_map.items():
            if nome in turma_lower:
                dias_indices.add(idx)
                
        if not dias_indices:
            return []
            
        hoje = datetime.now()
        ano = hoje.year
        mes = hoje.month
        
        _, num_dias = calendar.monthrange(ano, mes)
        datas = []
        for dia in range(1, num_dias + 1):
            dt = datetime(ano, mes, dia)
            if dt.weekday() in dias_indices:
                datas.append(dt.strftime('%d/%m/%Y'))
                
        return datas

    def construir_grid(self):
        """Cria a tabela de chamada com base nos dados recebidos."""
        self.chamada_widgets = {}
        self.chamada_undo_stack = [] # Reseta a pilha de desfazer ao reconstruir
        
        # Tenta obter o nível atualizado a partir da lista de turmas (cache) para garantir precisão
        nivel_turma = ""
        if self.turmas_data:
            turma_sel = self.chamada_turma_combo.get()
            horario_sel = self.chamada_horario_combo.get()
            prof_sel = self.chamada_prof_var.get()
            for t in self.turmas_data:
                if t.get('Turma') == turma_sel and t.get('Horário') == horario_sel and t.get('Professor') == prof_sel:
                    nivel_turma = t.get('Nível', '')
                    break

        # Fallback: Se não encontrou no cache, tenta pegar do primeiro aluno
        if not nivel_turma and self.chamada_data.get('alunos'):
            nivel_turma = self.chamada_data['alunos'][0].get('Nível', '')
        
        # Obtém nome do mês atual
        meses_pt = {1: 'JANEIRO', 2: 'FEVEREIRO', 3: 'MARÇO', 4: 'ABRIL', 5: 'MAIO', 6: 'JUNHO',
                    7: 'JULHO', 8: 'AGOSTO', 9: 'SETEMBRO', 10: 'OUTUBRO', 11: 'NOVEMBRO', 12: 'DEZEMBRO'}
        mes_atual = meses_pt.get(datetime.now().month, '')

        # Configura o grid dentro do scrollable frame
        self.chamada_scroll_frame.grid_columnconfigure(0, weight=1) # Coluna do nome agora é a 0

        # --- LINHA 0: Informações Superiores (Nível e Mês) ---
        # Nível acima do Nome
        ctk.CTkLabel(self.chamada_scroll_frame, text=nivel_turma, font=ctk.CTkFont(size=12, weight="bold"), text_color="gray").grid(row=0, column=0, padx=5, pady=(5,0), sticky="w")
        
        qtd_datas = len(self.chamada_data['datas'])
        col_trash = qtd_datas + 1
        col_note = qtd_datas + 2

        # Mês acima das Datas
        if qtd_datas > 0:
            ctk.CTkLabel(self.chamada_scroll_frame, text=mes_atual, font=ctk.CTkFont(size=12, weight="bold"), text_color="gray").grid(row=0, column=1, columnspan=qtd_datas, pady=(5,0), sticky="ew")

        # --- Botões de Controle (Limpar e Desfazer) na Linha 0 ---
        self.btn_limpar_chamada = ctk.CTkButton(self.chamada_scroll_frame, text="🧹", width=25, height=25,
                                                fg_color="transparent", hover_color="#bdc3c7", text_color="gray",
                                                font=ctk.CTkFont(size=12),
                                                command=self.limpar_chamada_atual)
        self.btn_limpar_chamada.grid(row=0, column=col_trash, padx=1, pady=(5,0))
        
        self.btn_desfazer = ctk.CTkButton(self.chamada_scroll_frame, text="\uE7A7", width=25, height=25,
                                          fg_color="transparent", hover_color="#bdc3c7", 
                                          text_color=("gray10", "gray90"), text_color_disabled="gray",
                                          font=ctk.CTkFont(family="Segoe MDL2 Assets", size=12),
                                          state="disabled",
                                          command=self.desfazer_ultima_acao)
        self.btn_desfazer.grid(row=0, column=col_note, padx=1, pady=(5,0))

        # --- LINHA 1: Cabeçalhos da Tabela ---
        lbl_nome = ctk.CTkLabel(self.chamada_scroll_frame, text="Nome", font=ctk.CTkFont(weight="bold"))
        lbl_nome.grid(row=1, column=0, padx=1, pady=1, sticky="ew")
        lbl_nome.bind("<Double-Button-1>", self.ordenar_chamada_por_nome)
        
        headers_datas = [d.split('/')[0] for d in self.chamada_data['datas']]
        for i, dia in enumerate(headers_datas):
            ctk.CTkLabel(self.chamada_scroll_frame, text=dia, font=ctk.CTkFont(weight="bold")).grid(row=1, column=i+1, padx=1, pady=1, sticky="ew")
        
        ctk.CTkLabel(self.chamada_scroll_frame, text="", width=20).grid(row=1, column=col_trash, padx=1, pady=1)
        ctk.CTkLabel(self.chamada_scroll_frame, text="", width=30).grid(row=1, column=col_note, padx=1, pady=1)

        # --- LINHA 2+: Dados dos Alunos ---
        for row_idx, aluno in enumerate(self.chamada_data['alunos'], start=2):
            nome_aluno = aluno['Nome']
            
            # Label do Nome (Coluna 0)
            nome_label = ctk.CTkLabel(self.chamada_scroll_frame, text=nome_aluno, anchor="w")
            nome_label.grid(row=row_idx, column=0, padx=5, pady=1, sticky="ew")

            self.chamada_widgets[nome_aluno] = {}
            
            # Contadores para lógica de ativação dos botões
            count_f = 0
            count_j = 0

            # Botões de status (Colunas 1 em diante)
            for col_idx, data_str in enumerate(self.chamada_data['datas'], start=1):
                valor_registrado = aluno.get(data_str, "")
                
                # Contabiliza faltas e justificativas
                if valor_registrado == 'f': count_f += 1
                if valor_registrado == 'j': count_j += 1
                
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
                                    height=25, # Altura fixa para evitar tremores
                                    text_color="white",
                                    font=ctk.CTkFont(weight="bold"))
                
                # A função de callback precisa de 'lambda' para capturar os valores corretos
                btn.configure(command=lambda v=status_var, b=btn, n=nome_aluno, d=data_str: self.mudar_status(v, b, n, d))
                btn.grid(row=row_idx, column=col_idx, padx=1, pady=1)

                self.chamada_widgets[nome_aluno][data_str] = {"var": status_var, "btn": btn}
            
            # --- Botão Lixeira (Exclusão) ---
            # Ativo apenas se tiver 3 ou mais faltas ('f')
            is_trash_active = count_f >= 3
            btn_trash = ctk.CTkButton(self.chamada_scroll_frame, text="\uE74D", width=20, height=25,
                                      font=ctk.CTkFont(family="Segoe MDL2 Assets", size=12),
                                      fg_color="#E74C3C" if is_trash_active else "transparent",
                                      text_color="white" if is_trash_active else "gray",
                                      state="normal" if is_trash_active else "disabled",
                                      hover_color="#c0392b",
                                      command=lambda a=aluno: self.confirmar_exclusao_aluno(a))
            btn_trash.grid(row=row_idx, column=col_trash, padx=2, pady=1)

            # --- Botão Anotação (Justificativa) ---
            # Ativo apenas se tiver pelo menos uma justificativa ('j')
            is_note_active = count_j > 0
            btn_note = ctk.CTkButton(self.chamada_scroll_frame, text="📝", width=20, height=25,
                                     fg_color="#F39C12" if is_note_active else "transparent",
                                     text_color="white" if is_note_active else "gray",
                                     state="normal" if is_note_active else "disabled",
                                     hover_color="#d35400",
                                     command=lambda a=aluno: self.abrir_anotacoes(a))
            btn_note.grid(row=row_idx, column=col_note, padx=2, pady=1)

            # Armazena os botões de ação para atualização em tempo real
            self.chamada_widgets[nome_aluno]["actions"] = {"trash": btn_trash, "note": btn_note}

    def _aplicar_status_visual(self, status_id, btn_widget):
        """Atualiza visualmente o botão de status."""
        estilo = STATUS_MAP[status_id]
        btn_widget.configure(text=estilo["text"], 
                             fg_color=estilo["fg_color"],
                             hover_color=estilo["hover_color"])

    def _registrar_undo(self, action_data):
        """Registra uma ação na pilha de desfazer."""
        self.chamada_undo_stack.append(action_data)
        if hasattr(self, 'btn_desfazer'):
            self.btn_desfazer.configure(state="normal")

    def limpar_chamada_atual(self):
        """Limpa todos os status da chamada atual."""
        if not self.chamada_widgets: return
        
        changes = []
        for nome, dados in self.chamada_widgets.items():
            for data_str, widget_info in dados.items():
                if data_str == "actions": continue
                
                current_val = widget_info["var"].get()
                if current_val != 0:
                    changes.append({
                        'aluno': nome,
                        'data': data_str,
                        'prev_val': current_val
                    })

        if not changes:
            messagebox.showinfo("Info", "A chamada já está limpa.")
            return

        if not messagebox.askyesno("Limpar Chamada", "Deseja limpar todos os registros desta chamada?"):
            return

        for item in changes:
            w_info = self.chamada_widgets[item['aluno']][item['data']]
            w_info["var"].set(0)
            self._aplicar_status_visual(0, w_info["btn"])
        
        affected_students = set(item['aluno'] for item in changes)
        for aluno in affected_students:
            self._atualizar_estado_botoes_acao(aluno)

        self._registrar_undo({'type': 'batch', 'changes': changes})

    def desfazer_ultima_acao(self):
        """Desfaz a última ação registrada."""
        if not self.chamada_undo_stack: return
        
        action = self.chamada_undo_stack.pop()
        
        if action['type'] == 'single':
            self._reverter_item(action['aluno'], action['data'], action['prev_val'])
        elif action['type'] == 'batch':
            for item in action['changes']:
                self._reverter_item(item['aluno'], item['data'], item['prev_val'])
        
        if not self.chamada_undo_stack:
            self.btn_desfazer.configure(state="disabled")

    def mudar_status(self, status_var, btn_widget, nome_aluno, data_str):
        """Cicla entre os status quando um botão é clicado."""
        old_status_id = status_var.get()
        novo_status_id = (old_status_id + 1) % len(STATUS_MAP)
        
        self._registrar_undo({'type': 'single', 'aluno': nome_aluno, 'data': data_str, 'prev_val': old_status_id})
        
        status_var.set(novo_status_id)
        self._aplicar_status_visual(novo_status_id, btn_widget)
        self._atualizar_estado_botoes_acao(nome_aluno)

    def _reverter_item(self, nome, data, prev_val):
        """Reverte um item específico para o valor anterior."""
        if nome in self.chamada_widgets and data in self.chamada_widgets[nome]:
            w_info = self.chamada_widgets[nome][data]
            w_info["var"].set(prev_val)
            self._aplicar_status_visual(prev_val, w_info["btn"])
            self._atualizar_estado_botoes_acao(nome)

    def _atualizar_estado_botoes_acao(self, nome_aluno):
        """Recalcula faltas e justificativas para ativar/desativar botões de ação em tempo real (incluindo desfazer)."""
        if nome_aluno not in self.chamada_widgets: return
        
        widgets = self.chamada_widgets[nome_aluno]
        count_f = 0
        count_j = 0
        
        for key, val in widgets.items():
            if key == "actions": continue
            status_id = val["var"].get()
            code = STATUS_MAP[status_id]["code"]
            if code == 'f': count_f += 1
            if code == 'j': count_j += 1
            
        actions = widgets.get("actions", {})
        btn_trash = actions.get("trash")
        btn_note = actions.get("note")
        
        if btn_trash:
            # Lógica da Lixeira: Ativa se >= 3 faltas. Desativa imediatamente se corrigir para menos.
            is_active = count_f >= 3
            btn_trash.configure(state="normal" if is_active else "disabled",
                                fg_color="#E74C3C" if is_active else "transparent",
                                text_color="white" if is_active else "gray",
                                hover_color="#c0392b")

        if btn_note:
            # Lógica da Nota: Ativa se tiver pelo menos 1 justificativa ('j'). Independente da lixeira.
            is_active = count_j > 0
            btn_note.configure(state="normal" if is_active else "disabled",
                               fg_color="#F39C12" if is_active else "transparent",
                               text_color="white" if is_active else "gray",
                               hover_color="#d35400")

    def ordenar_chamada_por_nome(self, event=None):
        """Ordena a lista de chamada pelo nome ao dar duplo clique no cabeçalho."""
        if not self.chamada_data or 'alunos' not in self.chamada_data:
            return

        # 1. Salva o estado atual dos botões (presença) antes de reordenar
        for aluno in self.chamada_data['alunos']:
            nome = aluno.get('Nome')
            if nome in self.chamada_widgets:
                for data_str, widget_info in self.chamada_widgets[nome].items():
                    if data_str == "actions": continue
                    status_id = widget_info["var"].get()
                    code = STATUS_MAP[status_id]["code"]
                    aluno[data_str] = code

        # 2. Alterna a ordenação e ordena a lista
        self.chamada_sort_reverse = not self.chamada_sort_reverse
        self.chamada_data['alunos'].sort(key=lambda x: x.get('Nome', '').lower(), reverse=self.chamada_sort_reverse)

        # 3. Limpa e reconstrói o grid
        for widget in self.chamada_scroll_frame.winfo_children():
            widget.destroy()
        self.construir_grid()

    def confirmar_exclusao_aluno(self, aluno):
        """Confirma e exclui o aluno se tiver 3 ou mais faltas."""
        msg = "Aviso: O aluno excluído poderá ser consultado na lista de exclusão. Tem certeza desta exclusão?"
        if messagebox.askyesno("Confirmar Exclusão", msg, icon='warning'):
            self.excluir_aluno(aluno)

    def excluir_aluno(self, aluno):
        """Envia requisição para excluir o aluno."""
        nome = aluno.get('Nome')
        if not nome: return
        try:
            encoded_name = quote(nome)
            response = requests.delete(f"{API_BASE_URL}/api/aluno/{encoded_name}")
            response.raise_for_status()
            messagebox.showinfo("Sucesso", f"Aluno {nome} excluído com sucesso.")
            self.iniciar_busca_alunos() # Atualiza a lista
        except requests.exceptions.RequestException as e:
            messagebox.showerror("Erro", f"Erro ao excluir aluno: {e}")

    def abrir_anotacoes(self, aluno):
        """Abre um card de anotações centralizado para o aluno."""
        # Cria uma janela Toplevel
        top = ctk.CTkToplevel(self)
        top.title(f"Anotações - {aluno.get('Nome')}")
        top.geometry("320x400")
        top.transient(self)
        
        # Centraliza a janela
        self.after(10, lambda: self._center_toplevel(top))
        
        ctk.CTkLabel(top, text=f"Justificativas: {aluno.get('Nome')}", font=ctk.CTkFont(weight="bold")).pack(pady=(15, 10))
        
        # Frame de entrada
        input_frame = ctk.CTkFrame(top)
        input_frame.pack(padx=10, pady=5, fill="x")
        
        ctk.CTkLabel(input_frame, text="Dia (00):").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        entry_cod = ctk.CTkEntry(input_frame, width=60, placeholder_text="00")
        entry_cod.grid(row=0, column=1, padx=5, pady=5, sticky="w")
        
        ctk.CTkLabel(input_frame, text="Justificativa:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        entry_just = ctk.CTkEntry(input_frame, width=200, placeholder_text="Descrição...")
        entry_just.grid(row=1, column=1, padx=5, pady=5, sticky="w")
        
        def salvar_nota():
            cod = entry_cod.get()
            just = entry_just.get()
            if not cod or not just:
                messagebox.showwarning("Aviso", "Preencha o código e a justificativa.", parent=top)
                return
            
            # Constrói a data completa usando o ano e mês vigentes
            hoje = datetime.now()
            try:
                dia = int(cod)
                data_completa = datetime(hoje.year, hoje.month, dia).strftime("%d/%m/%Y")
            except ValueError:
                messagebox.showwarning("Erro", "Dia inválido.", parent=top)
                return

            payload = {
                "Nome": aluno.get('Nome'),
                "Data": data_completa,
                "Motivo": just
            }

            try:
                response = requests.post(f"{API_BASE_URL}/api/justificativa", json=payload)
                response.raise_for_status()
                
                nova_nota = f"{cod.zfill(2)} - {just}"
                text_box.configure(state="normal")
                text_box.insert("end", f"{nova_nota}\n")
                text_box.configure(state="disabled")
                
                # Atualiza o objeto aluno localmente para persistência visual sem recarregar
                if aluno.get('Justificativas'):
                    aluno['Justificativas'] += f"\n{nova_nota}"
                else:
                    aluno['Justificativas'] = nova_nota

                entry_cod.delete(0, "end")
                entry_just.delete(0, "end")
            except requests.exceptions.RequestException as e:
                messagebox.showerror("Erro", f"Erro ao salvar justificativa: {e}", parent=top)

        ctk.CTkButton(input_frame, text="Salvar Anotação", command=salvar_nota).grid(row=2, column=0, columnspan=2, pady=10)
        
        # Área de visualização das notas existentes
        meses_pt = {1: 'Janeiro', 2: 'Fevereiro', 3: 'Março', 4: 'Abril', 5: 'Maio', 6: 'Junho',
                    7: 'Julho', 8: 'Agosto', 9: 'Setembro', 10: 'Outubro', 11: 'Novembro', 12: 'Dezembro'}
        mes_atual = meses_pt.get(datetime.now().month, '')
        
        ctk.CTkLabel(top, text=f"Histórico ({mes_atual}):", anchor="w").pack(padx=10, pady=(10, 0), anchor="w")
        text_box = ctk.CTkTextbox(top, height=200)
        text_box.pack(padx=10, pady=5, fill="both", expand=True)
        
        # Carrega notas existentes se houver (campo 'Justificativas' ou similar)
        if aluno.get('Justificativas'):
            text_box.insert("0.0", aluno.get('Justificativas'))
        text_box.configure(state="disabled")

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
                if data_str == "actions": continue
                status_id = widget_info["var"].get()
                status_code = STATUS_MAP[status_id]["code"]
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
                self.categorias_data = categorias_list # Atualiza o cache global da App
            except requests.exceptions.RequestException:
                categorias_list = []

            # Carrega turmas (se não estiver em cache) para definir o Nível corretamente
            turmas_list = self.turmas_data
            if not turmas_list:
                try:
                    resp_turmas = requests.get(f"{API_BASE_URL}/api/all-turmas")
                    resp_turmas.raise_for_status()
                    turmas_list = resp_turmas.json()
                    self.turmas_data = turmas_list
                except:
                    turmas_list = []

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
                aluno_normalizado = self._normalizar_dados_aluno(aluno, categorias_list, turmas_list)
                alunos[idx] = aluno_normalizado

            self.all_students_data = alunos # Armazena a lista processada e normalizada no cache

            
            # Após carregar, constrói o grid com TODOS os alunos
            def _update_ui_after_load():
                self._construir_grid_alunos(self.all_students_data)
            self.after(0, _update_ui_after_load)

        except requests.exceptions.RequestException as e:
            # Passa a exceção 'e' para a função de atualização da UI
            self.after(0, self._update_ui_error, e)

    def _normalizar_dados_aluno(self, aluno_data, categorias_list, turmas_list=None):
        """
        Centraliza a lógica de limpeza e padronização dos dados de um aluno.
        Garante que chaves conflitantes (ex: 'Aniversario' vs 'Data de Nascimento') sejam unificadas.
        Recalcula campos derivados (Idade, Categoria, Nível) para garantir consistência.
        """
        # 1. Unifica a data de nascimento
        keys_nasc = ['Aniversario', 'Aniversário', 'Data de Nascimento', 'data_nascimento', 'nascimento']
        data_nasc_val = next((aluno_data.get(k) for k in keys_nasc if aluno_data.get(k)), None)

        # 2. Unifica o telefone/whatsapp
        keys_tel = ['Whatsapp', 'whatsapp', 'Telefone', 'telefone', 'Celular', 'celular']
        telefone_val = next((aluno_data.get(k) for k in keys_tel if aluno_data.get(k)), None)

        # Limpa chaves duplicadas do dicionário para evitar confusão
        for k in keys_nasc + keys_tel:
            aluno_data.pop(k, None)

        aluno_data['Aniversario'] = data_nasc_val
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

        # 5. Define e adiciona Nível (Recuperação baseada na Turma)
        # Se o backend não salvou o Nível, redescobrimos pela Turma/Horário/Prof
        if turmas_list:
            turma_aluno = aluno_data.get('Turma')
            horario_aluno = aluno_data.get('Horário')
            prof_aluno = aluno_data.get('Professor')
            
            nivel_encontrado = '-'
            for t in turmas_list:
                if (t.get('Turma') == turma_aluno and 
                    t.get('Horário') == horario_aluno and 
                    t.get('Professor') == prof_aluno):
                    nivel_encontrado = t.get('Nível')
                    break
            aluno_data['Nível'] = nivel_encontrado

        # 6. Garante campos estáticos com valor padrão
        aluno_data.setdefault('Gênero', '')
        aluno_data.setdefault('ParQ', 'Não')

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
        self.alunos_sort_state = []
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
            
            filtered_data = [item for item in filtered_data if str(item.get(key) or '') in selected_values]

        return filtered_data

    def _construir_grid_alunos(self, alunos_para_exibir):
        """Constrói a grade de exibição na aba 'Alunos'."""
        for widget in self.alunos_scroll_frame.winfo_children():
            widget.destroy()
        self.alunos_grid_resizers.clear() # Limpa a lista de resizers antigos

        if not alunos_para_exibir:
            ctk.CTkLabel(self.alunos_scroll_frame, text="Nenhum aluno encontrado.").pack(pady=20)
            return

        # --- Lógica de Ordenação (Stable Sort / Múltiplos Níveis) ---
        # Itera sobre o histórico de ordenação do mais antigo para o mais recente (pilha).
        # Como o sort do Python é estável, a última ordenação aplicada prevalece,
        # mantendo a ordem anterior para itens iguais.
        if self.alunos_sort_state:
            # Mapeamentos para ordenação customizada
            nivel_order = {
                'Iniciação B': 0, 'Iniciação A': 1, 'Nível 1': 2, 'Nível 2': 3,
                'Nível 3': 4, 'Nível 4': 5, 'Adulto B': 6, 'Adulto A': 7
            }
            # Normaliza chaves para garantir match mesmo com espaços extras
            categoria_order = {
                'Pré-Mirim': 0, 'Mirim I': 1, 'Mirim II': 2, 'Petiz I': 3, 'Petiz II': 4,
                'Infantil I': 5, 'Infantil II': 6, 'Juvenil I': 7, 'Juvenil II': 8,
                'Júnior I': 9, 'Júnior II/Sênior': 10
            }

            def get_sort_value(aluno, sort_key):
                val = aluno.get(sort_key, '')
                if val is None: val = ''

                if sort_key == 'Nível':
                    return nivel_order.get(val, 99) # Valores não mapeados vão para o final
                if sort_key == 'Categoria':
                    if not isinstance(val, str): return (99, str(val))
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

            # Aplica as ordenações sequencialmente
            for sort_instruction in self.alunos_sort_state:
                key = sort_instruction['key']
                reverse = sort_instruction['reverse']
                alunos_para_exibir.sort(key=lambda a, k=key: get_sort_value(a, k), reverse=reverse)

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

        def create_header_widget(text, key, col_width):
            """Cria um único CTkButton que se adapta para parecer um Label ou um Botão."""
            display_text = text
            
            # Verifica se esta coluna está no histórico de ordenação
            sort_info = next((item for item in self.alunos_sort_state if item['key'] == key), None)
            is_sorted = sort_info is not None
            # Verifica se é a ordenação PRINCIPAL (a última da lista)
            is_primary_sort = self.alunos_sort_state and self.alunos_sort_state[-1]['key'] == key
            is_filtered = key in self.alunos_filter_state and self.alunos_filter_state[key]

            if is_sorted:
                sort_arrow = '▼' if sort_info['reverse'] else '▲'
                display_text = f"{text} {sort_arrow}"
            elif is_filtered:
                display_text += " ▾"

            # A solução é definir os parâmetros na criação, não no .configure()
            if is_sorted or is_filtered:
                # Botão ativo: com fundo, hover e espaçamento padrão
                widget = ctk.CTkButton(frame, text=display_text, text_color=("gray10", "gray90"),
                                     font=ctk.CTkFont(size=12, weight="bold" if is_primary_sort else "normal"), corner_radius=4,
                                     fg_color=("#e0e2e4", "#4a4d50"), hover_color=("#d3d5d7", "#5a5d60"),
                                     width=col_width)
            else:
                # Botão inativo: imita um Label, sem fundo, sem hover e sem espaçamento horizontal
                widget = ctk.CTkButton(frame, text=display_text, text_color=("gray10", "gray90"),
                                     font=ctk.CTkFont(size=12, weight="bold"), corner_radius=4,
                                     fg_color="transparent", hover=False, text_color_disabled="red",
                                     width=0) # O 'width=0' é a chave para remover o padding

            widget.configure(command=lambda k=key, w=widget: self._open_filter_menu(k, w))
            return widget

        for i, header_text in enumerate(headers):
            if not header_text: # Cabeçalho da coluna de ações
                ctk.CTkLabel(self.alunos_scroll_frame, text="Ações", font=ctk.CTkFont(size=12, weight="bold")).grid(row=0, column=i, padx=2, pady=4, sticky='ns')
                continue

            key = header_text
            header_widget = create_header_widget(header_text, key, width)
            header_widget.grid(row=0, column=i, padx=0, pady=4, sticky='ew')

            # Adiciona um redimensionador após cada cabeçalho, exceto o último
            if i < len(headers) - 1:
                resizer = ColumnResizer(frame, grid_layout=frame, column_index=i, app_instance=self) 
                resizer.grid(row=0, column=i, rowspan=len(alunos_para_exibir) + 2, sticky='nse')
                self.alunos_grid_resizers.append(resizer)

        # Linhas de Alunos
        for row_idx, aluno in enumerate(alunos_para_exibir, start=1):
            # Coluna 0: Nome (menos espaçamento à direita para aproximar do Nível)
            name_lbl = ctk.CTkLabel(self.alunos_scroll_frame, text=aluno.get('Nome', ''), anchor="w")
            name_lbl.grid(row=row_idx, column=0, padx=(5, 2), pady=2, sticky="ew")
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
        # Verifica se a chave já existe no histórico
        existing_sort = next((item for item in self.alunos_sort_state if item['key'] == key), None)

        if existing_sort:
            if existing_sort == self.alunos_sort_state[-1]:
                # Se for a chave principal atual, apenas inverte a direção
                existing_sort['reverse'] = not existing_sort['reverse']
            else:
                # Se já existe mas não é a principal, move para o final (torna principal) mantendo a direção
                self.alunos_sort_state.remove(existing_sort)
                self.alunos_sort_state.append(existing_sort)
        else:
            # Se é uma nova chave, adiciona ao final como principal (Ascendente)
            self.alunos_sort_state.append({'key': key, 'reverse': False})
        
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

        # --- CORREÇÃO: Coleta valores únicos da lista *atualmente filtrada*, não da lista completa ---
        # 1. Pega o filtro de busca por nome
        query = self.alunos_search_entry.get().lower()
        alunos_filtrados_nome = [aluno for aluno in self.all_students_data if query in aluno.get('Nome', '').lower()] if query else self.all_students_data

        # 2. Aplica os outros filtros de coluna, *exceto* o da coluna que estamos abrindo o menu
        dados_para_menu = alunos_filtrados_nome
        for filter_key, selected_values in self.alunos_filter_state.items():
            if filter_key != key and selected_values:
                dados_para_menu = [item for item in dados_para_menu if str(item.get(filter_key) or '') in selected_values]

        # 3. Coleta os valores únicos da lista resultante
        unique_values = sorted(list(set(str(aluno.get(key) or '') for aluno in dados_para_menu)))

        # --- CORREÇÃO: Não abre o menu se não houver valores únicos para exibir ---
        # Isso previne a criação de um menu vazio que poderia ter sua geometria inválida salva.
        if not unique_values:
            messagebox.showinfo("Filtro", f"Não há valores disponíveis para filtrar na coluna '{key}' com a seleção atual.", parent=self)
            return

        # Cria e exibe o menu
        self.active_filter_menu = FilterMenu(self, key, unique_values, button_widget, self._apply_filter_and_sort,
                                             active_filters=self.alunos_filter_state.get(key),
                                             cache_key=key,
                                             align="left")
        # O novo FilterMenu (Frame) se posiciona e se destrói sozinho.
        # A referência é limpa no seu próprio método destroy.

    def _apply_filter_and_sort(self, key, selected_values, sort_direction=None):
        """Callback para aplicar filtros e ordenação a partir do FilterMenu."""
        # Atualiza o estado do filtro
        if selected_values is not None:
            self.alunos_filter_state[key] = selected_values

        # Atualiza o estado da ordenação, se aplicável
        if sort_direction is not None:
            # Remove qualquer ordenação anterior dessa chave para reaplicar com a nova direção no topo
            self.alunos_sort_state = [s for s in self.alunos_sort_state if s['key'] != key]
            self.alunos_sort_state.append({'key': key, 'reverse': sort_direction == 'desc'})
        elif sort_direction is None and key in [s['key'] for s in self.alunos_sort_state]:
            # Se sort_direction for None (ex: limpar filtro), NÃO removemos a ordenação automaticamente
            # a menos que explicitamente desejado. 
            # No código original do FilterMenu, limpar filtro passava sort_direction=None.
            # Se quisermos que "Limpar Filtro" também limpe a ordenação dessa coluna:
            # self.alunos_sort_state = [s for s in self.alunos_sort_state if s['key'] != key]
            pass

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
        def _task():
            try:
                response = requests.get(f"{API_BASE_URL}/api/all-turmas")
                response.raise_for_status()
                turmas = response.json()
                self.after(0, lambda: self._preencher_tabela_turmas(turmas))
            except requests.exceptions.RequestException as e:
                self.after(0, lambda: self._exibir_erro_turmas(e))
        
        self.run_in_thread(_task)

    def _preencher_tabela_turmas(self, turmas):
        self.turmas_data = turmas  # Armazena em cache

        # --- Filtragem ---
        turmas_exibir = list(turmas)
        if self.turmas_filter_state:
            for key, selected_values in self.turmas_filter_state.items():
                if not selected_values: continue
                turmas_exibir = [t for t in turmas_exibir if str(t.get(key, '')) in selected_values]

        # --- Ordenação ---
        if self.turmas_sort_state:
            # Mapeamento para ordenação de Nível (reutilizando lógica se possível, ou definindo aqui)
            nivel_order = {
                'Iniciação B': 0, 'Iniciação A': 1, 'Nível 1': 2, 'Nível 2': 3,
                'Nível 3': 4, 'Nível 4': 5, 'Adulto B': 6, 'Adulto A': 7
            }
            
            def get_sort_value(item, sort_key):
                val = item.get(sort_key, '')
                if val is None: val = ''
                if sort_key == 'Nível':
                    return nivel_order.get(val, 99)
                if sort_key == 'Horário':
                    return val.split('-')[0]
                return str(val).lower()

            for sort_instruction in self.turmas_sort_state:
                key = sort_instruction['key']
                reverse = sort_instruction['reverse']
                turmas_exibir.sort(key=lambda t, k=key: get_sort_value(t, k), reverse=reverse)

        # --- Renderização ---
        for widget in self.turmas_scroll_frame.winfo_children():
            widget.destroy()
        
        try:
            headers = ["Turma", "Horário", "Nível", "Professor", "Qtd.", "Atalho", "Excluir"]
            filterable_headers = ["Turma", "Horário", "Nível", "Professor"]
            
            self.turmas_scroll_frame.grid_columnconfigure(0, weight=1)
            self.turmas_scroll_frame.grid_columnconfigure(1, weight=1)
            self.turmas_scroll_frame.grid_columnconfigure(2, weight=1)
            self.turmas_scroll_frame.grid_columnconfigure(3, weight=1)
            self.turmas_scroll_frame.grid_columnconfigure(4, weight=0) # Qtd (menor)
            self.turmas_scroll_frame.grid_columnconfigure(5, weight=0) # Atalho (menor)
            self.turmas_scroll_frame.grid_columnconfigure(6, weight=0) # Excluir (botão)

            for i, header in enumerate(headers):
                if header in filterable_headers:
                    # Cria botão de filtro
                    display_text = header
                    sort_info = next((item for item in self.turmas_sort_state if item['key'] == header), None)
                    is_sorted = sort_info is not None
                    is_filtered = header in self.turmas_filter_state and self.turmas_filter_state[header]

                    if is_sorted:
                        sort_arrow = '▼' if sort_info['reverse'] else '▲'
                        display_text = f"{header} {sort_arrow}"
                    elif is_filtered:
                        display_text += " ▾"

                    fg_color = ("#e0e2e4", "#4a4d50") if (is_sorted or is_filtered) else "transparent"
                    
                    btn = ctk.CTkButton(self.turmas_scroll_frame, text=display_text,
                                        font=ctk.CTkFont(weight="bold"),
                                        fg_color=fg_color,
                                        text_color=("gray10", "gray90"),
                                        hover_color=("#d3d5d7", "#5a5d60"),
                                        anchor="center",
                                        command=lambda k=header: self._open_turmas_filter_menu(k, self.turmas_scroll_frame.winfo_children()[-1])) 
                                        # Nota: O lambda captura o botão que acabamos de criar? Não, precisamos de referência.
                                        # Vamos criar o botão e atribuir o command depois ou usar uma factory.
                    
                    # Recriando o botão para ter a referência correta no command
                    btn = ctk.CTkButton(self.turmas_scroll_frame, text=display_text,
                                        font=ctk.CTkFont(weight="bold"),
                                        fg_color=fg_color,
                                        text_color=("gray10", "gray90"),
                                        hover_color=("#d3d5d7", "#5a5d60"),
                                        anchor="center")
                    btn.configure(command=lambda k=header, b=btn: self._open_turmas_filter_menu(k, b))
                    
                    if not (is_sorted or is_filtered):
                        btn.configure(hover=False)
                    
                    btn.grid(row=0, column=i, padx=5, pady=5, sticky="ew")
                else:
                    # Cabeçalho normal
                    anchor = "center" if header == "Qtd." else "w"
                    ctk.CTkLabel(self.turmas_scroll_frame, text=header, font=ctk.CTkFont(weight="bold"), anchor=anchor).grid(row=0, column=i, padx=5, pady=5, sticky="ew")

            for row_idx, turma in enumerate(turmas_exibir, start=1):
                # Turma
                turma_label = ctk.CTkLabel(self.turmas_scroll_frame, text=turma.get("Turma", ""), anchor="center")
                turma_label.grid(row=row_idx, column=0, padx=5, pady=5, sticky="ew")
                turma_label.bind("<Double-Button-1>", lambda e, t=turma, l=turma_label, c="Turma": self._iniciar_edicao_celula(t, l, c))

                # Horário
                horario_label = ctk.CTkLabel(self.turmas_scroll_frame, text=turma.get("Horário", ""), anchor="center")
                horario_label.grid(row=row_idx, column=1, padx=5, pady=5, sticky="ew")
                horario_label.bind("<Double-Button-1>", lambda e, t=turma, l=horario_label, c="Horário": self._iniciar_edicao_celula(t, l, c))

                # Nível
                nivel_label = ctk.CTkLabel(self.turmas_scroll_frame, text=turma.get("Nível", ""), anchor="center")
                nivel_label.grid(row=row_idx, column=2, padx=5, pady=5, sticky="ew")
                nivel_label.bind("<Double-Button-1>", lambda e, t=turma, l=nivel_label, c="Nível": self._iniciar_edicao_celula(t, l, c))

                # Professor
                prof_label = ctk.CTkLabel(self.turmas_scroll_frame, text=turma.get("Professor", ""), anchor="center")
                prof_label.grid(row=row_idx, column=3, padx=5, pady=5, sticky="ew")
                prof_label.bind("<Double-Button-1>", lambda e, t=turma, l=prof_label, c="Professor": self._iniciar_edicao_celula(t, l, c))

                ctk.CTkLabel(self.turmas_scroll_frame, text=str(turma.get("qtd.", 0)), anchor="center").grid(row=row_idx, column=4, padx=5, pady=5, sticky="ew")
                
                # Botão de atalho com ícone
                atalho_btn = ctk.CTkButton(self.turmas_scroll_frame, text="»", width=40, font=ctk.CTkFont(size=16, weight="bold"))
                atalho_btn.configure(command=lambda t=turma: self.usar_atalho_turma(t))
                atalho_btn.grid(row=row_idx, column=5, padx=5, pady=5)

                # Botão de Excluir (Lixeira)
                btn_excluir = ctk.CTkButton(self.turmas_scroll_frame, text="🗑️", width=40, fg_color="#E74C3C", hover_color="#c0392b", font=ctk.CTkFont(size=16))
                btn_excluir.configure(command=lambda t=turma: self.confirmar_exclusao_turma(t))
                btn_excluir.grid(row=row_idx, column=6, padx=5, pady=5)

        except Exception as e:
            print(f"Erro ao atualizar interface de turmas: {e}")

    def _open_turmas_filter_menu(self, key, button_widget):
        """Abre o menu de filtro para a aba Turmas."""
        if self.active_filter_menu and self.active_filter_menu.winfo_exists():
            is_same_button = getattr(self.active_filter_menu, 'button_widget', None) == button_widget
            self.active_filter_menu.destroy()
            if is_same_button: return
        self.after(10, lambda: self._create_turmas_filter_menu_safely(key, button_widget))

    def _create_turmas_filter_menu_safely(self, key, button_widget):
        if not self.turmas_data or self.active_filter_menu: return

        # Filtra baseado nas outras colunas para mostrar apenas opções válidas
        dados_para_menu = self.turmas_data
        for filter_key, selected_values in self.turmas_filter_state.items():
            if filter_key != key and selected_values:
                dados_para_menu = [item for item in dados_para_menu if str(item.get(filter_key) or '') in selected_values]

        unique_values = sorted(list(set(str(item.get(key) or '') for item in dados_para_menu)))

        if not unique_values:
            messagebox.showinfo("Filtro", f"Não há valores disponíveis para filtrar na coluna '{key}'.", parent=self)
            return

        self.active_filter_menu = FilterMenu(self, key, unique_values, button_widget, self._apply_turmas_filter_and_sort,
                                             active_filters=self.turmas_filter_state.get(key),
                                             cache_key=f"Turmas_{key}",
                                             align="center",
                                             show_sort_buttons=False)

    def _apply_turmas_filter_and_sort(self, key, selected_values, sort_direction=None):
        if selected_values is not None:
            self.turmas_filter_state[key] = selected_values
        
        if sort_direction is not None:
            self.turmas_sort_state = [s for s in self.turmas_sort_state if s['key'] != key]
            self.turmas_sort_state.append({'key': key, 'reverse': sort_direction == 'desc'})
        
        # Reconstrói a tabela usando os dados em cache
        self._preencher_tabela_turmas(self.turmas_data)

    def _exibir_erro_turmas(self, error):
        for widget in self.turmas_scroll_frame.winfo_children():
            widget.destroy()
        ctk.CTkLabel(self.turmas_scroll_frame, text=f"Erro ao carregar turmas: {error}").pack()

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

    def confirmar_exclusao_turma(self, turma_info):
        """Exibe aviso de atenção e confirma a exclusão da turma."""
        msg = (
            "ATENÇÃO: Tem certeza que deseja excluir esta turma?\n\n"
            "É IMPORTANTE transferir os alunos desta turma antes de realizar esta ação, "
            "pois eles ficarão sem turma vinculada.\n\n"
            "Deseja continuar com a exclusão?"
        )
        if messagebox.askyesno("Confirmar Exclusão", msg, icon='warning'):
            self.excluir_turma(turma_info)

    def excluir_turma(self, turma_info):
        """Chama a API para excluir a turma."""
        try:
            params = {
                "turma": turma_info["Turma"],
                "horario": turma_info["Horário"],
                "professor": turma_info["Professor"]
            }
            response = requests.delete(f"{API_BASE_URL}/api/turma", params=params)
            response.raise_for_status()
            messagebox.showinfo("Sucesso", "Turma excluída com sucesso!")
            self.carregar_lista_turmas() # Recarrega a lista para remover o item excluído
            self.carregar_filtros_iniciais() # Atualiza os filtros de busca para refletir a exclusão
        except requests.exceptions.RequestException as e:
            messagebox.showerror("Erro", f"Erro ao excluir turma: {e}")

    def _iniciar_edicao_celula(self, turma_info, label_widget, campo):
        """Substitui o Label por um Entry para edição de qualquer campo."""
        current_value = label_widget.cget("text")
        
        # Cria o Entry com o valor atual
        entry = ctk.CTkEntry(self.turmas_scroll_frame, width=label_widget.winfo_width())
        entry.insert(0, current_value)
        
        # Obtém a posição do grid do label atual
        grid_info = label_widget.grid_info()
        
        # Esconde o label e mostra o entry no mesmo lugar
        label_widget.grid_forget()
        entry.grid(row=grid_info['row'], column=grid_info['column'], padx=5, pady=5, sticky="ew")
        entry.focus_set() # Foca no entry para digitar imediatamente
        
        # Define callbacks para Salvar (Enter) ou Cancelar (Esc/FocusOut)
        entry.bind("<Return>", lambda e: self._salvar_edicao_celula(entry, turma_info, label_widget, campo))
        entry.bind("<Escape>", lambda e: self._cancelar_edicao_celula(entry, label_widget))
        entry.bind("<FocusOut>", lambda e: self._cancelar_edicao_celula(entry, label_widget))

    def _cancelar_edicao_celula(self, entry_widget, label_widget):
        """Cancela a edição e restaura o Label original."""
        entry_widget.destroy()
        # Restaura o label usando as configurações originais (assumindo coluna 0)
        self.carregar_lista_turmas() # Recarrega para garantir consistência visual e de dados

    def _propagar_edicao_para_alunos(self, old_turma, old_horario, old_professor, campo_editado, novo_valor):
        """Atualiza os alunos que pertencem à turma editada."""
        try:
            # Garante que temos a lista completa de alunos para buscar quem atualizar
            # Se o cache estiver vazio, busca do servidor
            if not self.all_students_data:
                response = requests.get(f"{API_BASE_URL}/api/all-alunos")
                response.raise_for_status()
                self.all_students_data = response.json()

            # Filtra os alunos que pertencem à turma ANTIGA (antes da edição)
            alunos_afetados = [
                a for a in self.all_students_data 
                if a.get('Turma') == old_turma and 
                   a.get('Horário') == old_horario and 
                   a.get('Professor') == old_professor
            ]

            # Atualiza cada aluno encontrado
            for aluno in alunos_afetados:
                # Atualiza o campo no objeto local
                aluno[campo_editado] = novo_valor
                
                # Envia atualização para a API
                nome = aluno.get('Nome')
                if nome:
                    try:
                        encoded_name = quote(nome)
                        requests.put(f"{API_BASE_URL}/api/aluno/{encoded_name}", json=aluno)
                    except Exception:
                        pass # Continua para o próximo aluno mesmo se um falhar

            # Invalida o cache para forçar recarregamento na UI quando o usuário for para a aba Alunos
            self.all_students_data = None
            
        except Exception as e:
            print(f"Erro na propagação de edição: {e}")

    def _salvar_edicao_celula(self, entry_widget, turma_info, label_widget, campo):
        """Envia o novo valor para a API."""
        novo_valor = entry_widget.get()
        
        endpoint = ""
        request_kwargs = {}

        # Captura valores antigos para identificar os alunos a serem atualizados
        old_turma = turma_info.get("Turma") or ""
        old_horario = turma_info.get("Horário") or ""
        old_professor = turma_info.get("Professor") or ""

        if campo == "Nível":
            # Endpoint específico existente para nível
            endpoint = "/api/turma/nivel"
            request_kwargs = {
                "json": {
                    "turma": turma_info.get("Turma") or "",
                    "horario": turma_info.get("Horário") or "",
                    "professor": turma_info.get("Professor") or "",
                    "novo_nivel": novo_valor
                }
            }
        else:
            # Endpoint geral para alteração de chaves (Turma, Horário, Professor)
            endpoint = "/api/turma"
            
            # CORREÇÃO: Estrutura ajustada conforme erro 422 (espera old_* e new_data no corpo)
            payload = {
                "old_turma": turma_info.get("Turma") or "",
                "old_horario": turma_info.get("Horário") or "",
                "old_professor": turma_info.get("Professor") or "",
                "new_data": {
                    "Turma": novo_valor if campo == "Turma" else (turma_info.get("Turma") or ""),
                    "Horário": novo_valor if campo == "Horário" else (turma_info.get("Horário") or ""),
                    "Nível": turma_info.get("Nível") or "",
                    "Professor": novo_valor if campo == "Professor" else (turma_info.get("Professor") or ""),
                    "Atalho": turma_info.get("Atalho") or "",
                    "Data_Inicio": turma_info.get("Data de Início") or ""
                }
            }
            request_kwargs = {"json": payload}

        try:
            response = requests.put(f"{API_BASE_URL}{endpoint}", **request_kwargs)
            response.raise_for_status()
            
            # --- PROPAGAÇÃO: Atualiza os alunos desta turma em background ---
            self.run_in_thread(lambda: self._propagar_edicao_para_alunos(
                old_turma, old_horario, old_professor, campo, novo_valor
            ))

            # Sucesso: Recarrega a lista para mostrar o dado atualizado e restaurar a UI
            self.carregar_lista_turmas()
            self.carregar_filtros_iniciais() # Atualiza filtros se mudou algo relevante
            
        except requests.exceptions.RequestException as e:
            error_msg = f"Erro ao atualizar {campo}: {e}"
            try:
                if e.response is not None:
                    detail = e.response.json().get('detail')
                    if detail:
                        error_msg += f"\nDetalhes: {detail}"
            except:
                pass
            messagebox.showerror("Erro", error_msg)
            self._cancelar_edicao_celula(entry_widget, label_widget)

    # --- MÉTODOS PARA A ABA EXCLUSÕES ---
    def carregar_lista_exclusoes(self):
        """Busca a lista de alunos excluídos do backend."""
        def _task():
            try:
                response = requests.get(f"{API_BASE_URL}/api/exclusoes")
                response.raise_for_status()
                data = response.json()
                self.after(0, lambda: self.construir_grid_exclusoes(data))
            except requests.exceptions.RequestException as e:
                self.after(0, lambda err=e: self._exibir_erro_exclusoes(err))
        self.run_in_thread(_task)

    def _exibir_erro_exclusoes(self, error):
        for widget in self.exclusoes_scroll_frame.winfo_children(): widget.destroy()
        ctk.CTkLabel(self.exclusoes_scroll_frame, text=f"Erro ao carregar exclusões: {error}").pack(pady=20)

    def construir_grid_exclusoes(self, alunos_excluidos):
        """Constrói a tabela de alunos excluídos."""
        for widget in self.exclusoes_scroll_frame.winfo_children():
            widget.destroy()

        if not alunos_excluidos:
            ctk.CTkLabel(self.exclusoes_scroll_frame, text="Nenhum registro de exclusão encontrado.").pack(pady=20)
            return

        # Cabeçalhos
        headers = ["Nome", "Turma", "Horário", "Professor", "Data Exclusão", "Ações"]
        self.exclusoes_scroll_frame.grid_columnconfigure(0, weight=1) # Nome expande
        self.exclusoes_scroll_frame.grid_columnconfigure((1,2,3,4), weight=0, minsize=100)
        self.exclusoes_scroll_frame.grid_columnconfigure(5, weight=0, minsize=120)

        for i, h in enumerate(headers):
            ctk.CTkLabel(self.exclusoes_scroll_frame, text=h, font=ctk.CTkFont(weight="bold")).grid(row=0, column=i, padx=5, pady=5, sticky="ew")

        meses_pt_abbr = {1: 'Jan', 2: 'Fev', 3: 'Mar', 4: 'Abr', 5: 'Mai', 6: 'Jun',
                         7: 'Jul', 8: 'Ago', 9: 'Set', 10: 'Out', 11: 'Nov', 12: 'Dez'}

        for idx, aluno in enumerate(alunos_excluidos, start=1):
            # Formata Data de Exclusão (mmm/aaaa)
            data_excl = aluno.get("Data Exclusão") or aluno.get("deleted_at")
            data_fmt = "-"
            if data_excl:
                try:
                    # Tenta parsear ISO ou formato padrão
                    dt = datetime.fromisoformat(str(data_excl).replace('Z', ''))
                    data_fmt = f"{meses_pt_abbr.get(dt.month, '')}/{dt.year}"
                except ValueError:
                    data_fmt = str(data_excl)

            ctk.CTkLabel(self.exclusoes_scroll_frame, text=aluno.get("Nome", ""), anchor="w").grid(row=idx, column=0, padx=5, pady=2, sticky="ew")
            ctk.CTkLabel(self.exclusoes_scroll_frame, text=aluno.get("Turma", ""), anchor="center").grid(row=idx, column=1, padx=5, pady=2)
            ctk.CTkLabel(self.exclusoes_scroll_frame, text=aluno.get("Horário", ""), anchor="center").grid(row=idx, column=2, padx=5, pady=2)
            ctk.CTkLabel(self.exclusoes_scroll_frame, text=aluno.get("Professor", ""), anchor="center").grid(row=idx, column=3, padx=5, pady=2)
            ctk.CTkLabel(self.exclusoes_scroll_frame, text=data_fmt, anchor="center").grid(row=idx, column=4, padx=5, pady=2)

            # Botões de Ação
            actions_frame = ctk.CTkFrame(self.exclusoes_scroll_frame, fg_color="transparent")
            actions_frame.grid(row=idx, column=5, padx=5, pady=2)

            ctk.CTkButton(actions_frame, text="ver", width=40, height=22, font=ctk.CTkFont(size=11),
                          fg_color="transparent", border_width=1,
                          command=lambda a=aluno: self.open_view_student_window(a)).pack(side="left", padx=2)
            
            ctk.CTkButton(actions_frame, text="restaurar", width=60, height=22, font=ctk.CTkFont(size=11),
                          fg_color="#2ECC71", hover_color="#27ae60", text_color="white",
                          command=lambda a=aluno: self.open_restore_student_window(a)).pack(side="left", padx=2)

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

    def open_restore_student_window(self, student_data):
        """Abre a janela de formulário em modo de restauração."""
        if self.add_student_toplevel is not None and self.add_student_toplevel.winfo_exists():
            self.add_student_toplevel.lift()
            return

        form_data = {
            "turmas": self.chamada_turma_combo.cget('values'),
            "horarios": self.chamada_horario_combo.cget('values'),
            "professores": [rb.cget('text') for rb in self.chamada_prof_frame.winfo_children() if isinstance(rb, ctk.CTkRadioButton)],
        }
        self.add_student_toplevel = AddStudentToplevel(self, form_data, self.on_student_added, restore_data=student_data)

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
        # 3. Se estiver na aba de exclusões, recarrega ela também
        if self.tab_view.get() == "Exclusões":
            self.carregar_lista_exclusoes()
        else:
            # Muda para a aba de alunos e recarrega a lista
            self.show_view("Alunos")
        # 4. Limpa a referência da janela Toplevel
        self.add_student_toplevel = None
        self.edit_student_toplevel = None

    def open_add_turma_window(self):
        """Abre uma janela Toplevel para adicionar uma nova turma."""
        if self.add_turma_toplevel is not None and self.add_turma_toplevel.winfo_exists():
            self.add_turma_toplevel.lift()
            return
        
        self.add_turma_toplevel = AddTurmaToplevel(self, self.on_turma_added)

    def on_turma_added(self):
        """Callback executado quando uma turma é adicionada com sucesso."""
        self.carregar_lista_turmas()
        self.carregar_filtros_iniciais() # Atualiza os filtros de busca com a nova turma/professor
        self.add_turma_toplevel = None


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
    def __init__(self, master, form_data, on_success_callback, edit_data=None, restore_data=None):
        super().__init__(master)
        self.master_app = master
        self.form_data = form_data
        self.on_success = on_success_callback
        self.edit_data = edit_data
        self.restore_data = restore_data
        self.is_edit_mode = edit_data is not None
        self.is_restore_mode = restore_data is not None

        if self.is_edit_mode:
            self.title(f"Editar Aluno - {edit_data.get('Nome', '')}")
        elif self.is_restore_mode:
            self.title(f"Restaurar Aluno - {restore_data.get('Nome', '')}")
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

        # Restaura geometria salva ou centraliza
        if "add_student" in self.master_app.window_geometries:
            self.geometry(self.master_app.window_geometries["add_student"])
        else:
            self.after(10, lambda: self.master_app._center_toplevel(self))
        self.after(100, lambda: self.widgets['nome'].focus_set())

    def _on_close(self):
        """Libera o foco e destrói a janela, limpando a referência na aplicação principal."""
        try:
            self.master_app.window_geometries["add_student"] = self.geometry() # Salva geometria ao fechar
        except Exception:
            pass
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
        cancel_text = "Limpar" if not (self.is_edit_mode or self.is_restore_mode) else "Cancelar"
        cancel_command = self._clear_personal_info_fields if not (self.is_edit_mode or self.is_restore_mode) else self._on_close
        cancel_button = ctk.CTkButton(button_frame, text=cancel_text, command=cancel_command,
                                      fg_color="transparent", border_width=1,
                                      height=40)
        cancel_button.grid(row=0, column=0, padx=(0, 5), sticky="ew")
        # --- Botão Adicionar/Salvar ---
        if self.is_restore_mode:
            add_text = "Restaurar Aluno"
        else:
            add_text = "Adicionar Aluno" if not self.is_edit_mode else "Salvar Alterações"
            
        add_button = ctk.CTkButton(button_frame, text=add_text, command=self._submit, height=40)
        add_button.grid(row=0, column=1, padx=(5, 0), sticky="ew")

        if self.is_edit_mode or self.is_restore_mode:
            # Se for restauração, usamos os dados de restore para preencher
            if self.is_restore_mode:
                self.edit_data = self.restore_data 
            self._populate_form_for_edit()

        # Navegação com Enter
        self._set_enter_navigation()
        on_field_change() # Inicializa os campos derivados

    def _populate_form_for_edit(self):
        """Preenche o formulário com os dados do aluno para edição."""
        if not self.edit_data:
            return

        self.widgets['nome'].insert(0, self.edit_data.get('Nome') or '')
        self.widgets['genero'].set(self.edit_data.get('Gênero') or '')

        # Formata a data de nascimento para dd/mm/YYYY
        data_nasc_str = self.edit_data.get('Aniversario') # Já foi normalizado
        if data_nasc_str:
            self.widgets['data_nasc'].insert(0, self.master_app._formatar_data_para_exibicao(str(data_nasc_str)))

        tel = self.edit_data.get('Whatsapp') or ''
        self.widgets['telefone'].insert(0, tel)
        self.widgets['turma'].set(self.edit_data.get('Turma') or '')
        self.widgets['horario'].set(self.edit_data.get('Horário') or '')
        self.widgets['prof_var'].set(self.edit_data.get('Professor') or '')
        self.widgets['parq_var'].set(self.edit_data.get('ParQ') or 'Sim')

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
            "Telefone": self.widgets['telefone'].get(), # Envia também como 'Telefone' para garantir compatibilidade com backend/Excel
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
                # Identifica o aluno pelo Nome original (e Aniversário), conforme solicitado
                # Identifica o aluno pelo Nome original, codificando para URL (ex: Zé do Pé -> Z%C3%A9%20do%20P%C3%A9)
                original_name = self.edit_data.get('Nome')
                original_dob = self.edit_data.get('Aniversario')

                if not original_name:
                    messagebox.showerror("Erro", "Nome original não encontrado. Não é possível identificar o aluno para edição.", parent=self)
                    return

                # Usa quote para garantir que espaços e acentos no nome não quebrem a URL
                encoded_name = quote(original_name)
                response = requests.put(f"{API_BASE_URL}/api/aluno/{encoded_name}", json=data)
                success_message = f"Dados de '{data['Nome']}' salvos com sucesso!"
            elif self.is_restore_mode:
                # Endpoint para RESTAURAR um aluno (move de exclusões para alunos)
                # Assume-se que o backend implementa esta lógica
                response = requests.post(f"{API_BASE_URL}/api/restaurar", json=data)
                success_message = f"Aluno '{data['Nome']}' restaurado com sucesso!"
            else:
                # Endpoint para CRIAR um novo aluno
                response = requests.post(f"{API_BASE_URL}/api/aluno", json=data)
                success_message = f"Aluno '{data['Nome']}' adicionado com sucesso!"

            response.raise_for_status()
            
            messagebox.showinfo("Sucesso", success_message, parent=self)

            # Chama o callback de sucesso na classe App
            if self.on_success:
                self.on_success(data)
            
            if self.is_edit_mode or self.is_restore_mode:
                self._on_close() # Fecha a janela após salvar
            else:
                # Limpa os campos pessoais para a próxima adição, mantendo os da turma
                self._clear_personal_info_fields()
            
        except requests.exceptions.RequestException as e:
            action = "salvar as alterações" if self.is_edit_mode else "adicionar o aluno"
            if self.is_restore_mode:
                action = "restaurar o aluno"
            elif self.is_edit_mode:
                action = "salvar as alterações"
            else:
                action = "adicionar o aluno"
            error_msg = f"Não foi possível {action}."

            if e.response is not None:
                if e.response.status_code == 404:
                    url_tentada = e.response.request.url if e.response.request else "URL desconhecida"
                    error_msg += f"\n\nErro 404 (Não Encontrado):\nO servidor não encontrou o aluno na URL:\n{url_tentada}\n\nVerifique se o nome do aluno no banco é exatamente '{self.edit_data.get('Nome')}'."
                else:
                    error_msg += f"\nStatus Code: {e.response.status_code}"
            
            error_msg += f"\n\nErro técnico: {e}"

            try:
                if e.response is not None:
                    error_detail = e.response.json().get('detail', '')
                    if error_detail:
                        error_msg += f"\nDetalhe do Servidor: {error_detail}"
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
        categorias_data = self.master_app.categorias_data # Usa sempre o cache mais atualizado da App
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

# --- NOVA CLASSE PARA O FORMULÁRIO DE ADIÇÃO DE TURMA ---
class AddTurmaToplevel(ctk.CTkToplevel):
    def __init__(self, master, on_success_callback):
        super().__init__(master)
        self.master_app = master
        self.on_success = on_success_callback

        self.title("Adicionar Nova Turma")
        self.geometry("400x350")
        self.transient(master)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        
        self.widgets = {}
        self._build_form()
        
        # Restaura geometria salva ou centraliza
        if "add_turma" in self.master_app.window_geometries:
            self.geometry(self.master_app.window_geometries["add_turma"])
        else:
            self.after(10, lambda: self.master_app._center_toplevel(self))

    def _on_close(self):
        """Salva a geometria e fecha a janela."""
        self.master_app.window_geometries["add_turma"] = self.geometry()
        self.destroy()
        self.master_app.add_turma_toplevel = None

    def _build_form(self):
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.pack(padx=20, pady=20, fill="both", expand=True)
        frame.grid_columnconfigure(0, weight=1)

        # Campos
        ctk.CTkLabel(frame, text="Turma:", anchor="w").grid(row=0, column=0, sticky="ew", pady=(0, 2))
        self.widgets['turma'] = ctk.CTkEntry(frame, placeholder_text="Ex: Segunda e Quarta")
        self.widgets['turma'].grid(row=1, column=0, sticky="ew", pady=(0, 10))

        ctk.CTkLabel(frame, text="Horário (só nºs):", anchor="w").grid(row=2, column=0, sticky="ew", pady=(0, 2))
        self.widgets['horario'] = ctk.CTkEntry(frame, placeholder_text="00h00")
        self.widgets['horario'].grid(row=3, column=0, sticky="ew", pady=(0, 10))
        self.widgets['horario'].bind("<KeyRelease>", self._format_time_entry)

        ctk.CTkLabel(frame, text="Nível:", anchor="w").grid(row=4, column=0, sticky="ew", pady=(0, 2))
        self.widgets['nivel'] = ctk.CTkEntry(frame, placeholder_text="Ex: Nível 1")
        self.widgets['nivel'].grid(row=5, column=0, sticky="ew", pady=(0, 10))

        ctk.CTkLabel(frame, text="Professor(a):", anchor="w").grid(row=6, column=0, sticky="ew", pady=(0, 2))
        self.widgets['professor'] = ctk.CTkEntry(frame, placeholder_text="Nome do Professor")
        self.widgets['professor'].grid(row=7, column=0, sticky="ew", pady=(0, 20))

        # Botão Salvar
        ctk.CTkButton(frame, text="Salvar Turma", command=self._submit, height=40).grid(row=8, column=0, sticky="ew")

    def _format_time_entry(self, event):
        """Aplica máscara 00h00 no campo de horário."""
        if event.keysym in ("BackSpace", "Delete"): return
        entry = event.widget
        text = entry.get()
        digits = "".join(filter(str.isdigit, text))
        
        formatted = digits
        if len(digits) >= 2:
            formatted = digits[:2] + "h" + digits[2:4]
        
        if text != formatted:
            entry.delete(0, "end")
            entry.insert(0, formatted)

    def _submit(self):
        data = {
            "Turma": self.widgets['turma'].get(),
            "Horário": self.widgets['horario'].get(),
            "Nível": self.widgets['nivel'].get(),
            "Professor": self.widgets['professor'].get()
        }

        if not all(data.values()):
            messagebox.showwarning("Aviso", "Preencha todos os campos.", parent=self)
            return

        try:
            # Ajustado para /api/turma (singular) para manter consistência com DELETE e PUT
            response = requests.post(f"{API_BASE_URL}/api/turma", json=data)
            response.raise_for_status()
            messagebox.showinfo("Sucesso", "Turma adicionada com sucesso!", parent=self)
            self.on_success()
            self._on_close()
        except requests.exceptions.RequestException as e:
            error_msg = f"Erro ao adicionar turma.\n\nErro técnico: {e}"
            try:
                if e.response is not None:
                    if e.response.status_code == 404:
                        error_msg += f"\n\nErro 404: Rota não encontrada ({e.response.url})."
                    elif e.response.status_code == 405:
                        error_msg += f"\n\nErro 405: Método não permitido em ({e.response.url})."
                    error_detail = e.response.json().get('detail', '')
                    if error_detail:
                        error_msg += f"\n\nDetalhe do Servidor: {error_detail}"
            except:
                pass
            messagebox.showerror("Erro", error_msg, parent=self)

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
            
            if key == "Whatsapp" and value:
                wa_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
                wa_frame.grid(row=row, column=1, padx=0, pady=4, sticky="ew")
                ctk.CTkLabel(wa_frame, text=str(value), anchor="w").pack(side="left")
                
                digits = "".join(filter(str.isdigit, str(value)))
                if digits:
                    link = f"https://wa.me/55{digits}"
                    ctk.CTkButton(wa_frame, text="💬", width=30, height=20, fg_color="#25D366", hover_color="#128C7E",
                                  command=lambda l=link: webbrowser.open(l)).pack(side="left", padx=(10, 0))
            else:
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
        # Verifica se o modo de edição está ativo
        if not self.master_menu.master_app.alunos_grid_edit_mode.get():
            return

        """Captura a posição inicial do mouse e a largura atual do menu."""
        self._start_x = event.x_root
        self._start_width = self.master_menu.winfo_width()
        self._start_menu_x = self.master_menu.winfo_x()

    def _on_drag(self, event):
        # Verifica se o modo de edição está ativo
        if not self.master_menu.master_app.alunos_grid_edit_mode.get():
            return

        """Calcula a nova largura com base no movimento do mouse e redimensiona o menu."""
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

    def __init__(self, master, key, values, button_widget, callback, active_filters=None, cache_key=None, align="left", show_sort_buttons=True):
        # O master agora é a janela principal da aplicação (App).
        # A altura será definida depois que o conteúdo for criado.
        super().__init__(master, corner_radius=8, border_width=1)

        self.key = key
        self.cache_key = cache_key if cache_key else key
        self.align = align
        self.show_sort_buttons = show_sort_buttons
        self.callback = callback
        self.button_widget = button_widget # Armazena o botão que abriu o menu
        self.master_app = master

        # --- Variáveis de estado ---
        # Se não houver filtro ativo (None), todos os valores são selecionados por padrão.
        initial_state = {value: tk.BooleanVar(value=True) for value in values} if active_filters is None else \
                        {value: tk.BooleanVar(value=value in active_filters) for value in values}
        self.check_vars = initial_state

        # Define um padding horizontal menor para todos os frames internos
        inner_padx = 3

        # --- Botões de Ordenação ---
        if self.show_sort_buttons:
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

        # Verifica se há geometria em cache para esta coluna e a utiliza
        cached_geometry = self.master_app.filter_menu_geometry_cache.get(self.cache_key)
        
        button_width = button_widget.winfo_width()
        default_width = max(200, button_width)
        initial_width = cached_geometry.get('width', default_width) if cached_geometry else default_width

        button_x_rel = button_widget.winfo_rootx() - master.winfo_rootx()
        default_y = button_widget.winfo_rooty() - master.winfo_rooty() + button_widget.winfo_height()
        
        # Calcula X (Centralizado ou Alinhado à Esquerda)
        if self.align == "center":
            default_x = button_x_rel + (button_width // 2) - (initial_width // 2)
        else:
            default_x = button_x_rel + 5
        
        # Ajuste simples para não sair da tela (esquerda/direita)
        master_width = master.winfo_width()
        default_x = max(5, min(default_x, master_width - initial_width - 5))

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

        # Adiciona os "puxadores" de redimensionamento (sempre ativos)
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
        # Salva a geometria (apenas se em modo de edição)
        # --- CORREÇÃO: Adiciona verificação de altura mínima antes de salvar a geometria ---
        # Isso impede que uma geometria inválida (ex: altura 0) seja salva no config.json.
        if self.winfo_exists() and self.winfo_height() > 50:
            if self.master_app.alunos_grid_edit_mode.get():
                self.master_app.filter_menu_geometry_cache[self.cache_key] = {
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
