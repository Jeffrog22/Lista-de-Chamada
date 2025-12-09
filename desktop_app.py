import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox
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
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # --- 1. SIDEBAR (PAINEL LATERAL) ---
        self.sidebar_frame = ctk.CTkFrame(self, width=250, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(5, weight=1) # Espaço para empurrar o botão de salvar para baixo

        # --- 1.0. Botão para recolher/expandir sidebar ---
        self.sidebar_expanded = True
        self.toggle_sidebar_button = ctk.CTkButton(self.sidebar_frame, text="☰", width=30, font=ctk.CTkFont(size=20), command=self.toggle_sidebar)
        self.toggle_sidebar_button.grid(row=0, column=0, padx=(10, 0), pady=(10,0), sticky="w")


        # --- 1.1. Frame do Menu Principal (visível no início) ---
        self.main_menu_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        self.main_menu_frame.grid(row=1, column=0, sticky="nsew")
        self.main_menu_label = ctk.CTkLabel(self.main_menu_frame, text="Menu Principal", font=ctk.CTkFont(size=20, weight="bold"))
        self.main_menu_label.grid(row=0, column=0, padx=20, pady=(20, 10))
        self.chamada_button = ctk.CTkButton(self.main_menu_frame, text="Chamada", command=lambda: self.show_view("Chamada"))
        self.chamada_button.grid(row=1, column=0, padx=20, pady=10, sticky="ew")
        self.alunos_button = ctk.CTkButton(self.main_menu_frame, text="Alunos", command=lambda: self.show_view("Alunos"))
        self.alunos_button.grid(row=2, column=0, padx=20, pady=10, sticky="ew")
        self.turmas_button = ctk.CTkButton(self.main_menu_frame, text="Turmas", command=lambda: self.show_view("Turmas"))
        self.turmas_button.grid(row=3, column=0, padx=20, pady=10, sticky="ew")

        # --- 1.2. Frame do Menu de Controle da CHAMADA (inicialmente oculto) ---
        self.chamada_control_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        # (grid é chamado em show_view)
        self.chamada_control_label = ctk.CTkLabel(self.chamada_control_frame, text="Controle de Chamada", font=ctk.CTkFont(size=16, weight="bold"))
        self.chamada_control_label.grid(row=0, column=0, columnspan=2, padx=20, pady=(20, 10))
        self.chamada_turma_combo = ctk.CTkComboBox(self.chamada_control_frame, values=["Carregando..."])
        self.chamada_turma_combo.grid(row=1, column=0, columnspan=2, padx=20, pady=10, sticky="ew")
        self.chamada_horario_combo = ctk.CTkComboBox(self.chamada_control_frame, values=["Carregando..."])
        self.chamada_horario_combo.grid(row=2, column=0, columnspan=2, padx=20, pady=10, sticky="ew")
        
        self.chamada_prof_var = tk.StringVar()
        self.chamada_prof_label = ctk.CTkLabel(self.chamada_control_frame, text="Professor(a):")
        self.chamada_prof_label.grid(row=3, column=0, columnspan=2, padx=20, pady=(10,0), sticky="w")
        self.chamada_prof_dani = ctk.CTkRadioButton(self.chamada_control_frame, text="Daniela", variable=self.chamada_prof_var, value="Daniela")
        self.chamada_prof_dani.grid(row=4, column=0, padx=(20,5), pady=5, sticky="w")
        self.chamada_prof_jeff = ctk.CTkRadioButton(self.chamada_control_frame, text="Jefferson", variable=self.chamada_prof_var, value="Jefferson")
        self.chamada_prof_jeff.grid(row=4, column=1, padx=(5,20), pady=5, sticky="w")

        self.chamada_buscar_button = ctk.CTkButton(self.chamada_control_frame, text="Buscar Alunos", command=self.iniciar_busca_alunos)
        self.chamada_buscar_button.grid(row=5, column=0, columnspan=2, padx=20, pady=10, sticky="ew")
        self.chamada_salvar_button = ctk.CTkButton(self.chamada_control_frame, text="Salvar Alterações", command=self.iniciar_salvar_chamada, fg_color="#007bff", hover_color="#0056b3")
        self.chamada_salvar_button.grid(row=6, column=0, columnspan=2, padx=20, pady=10, sticky="ew")
        self.chamada_back_button = ctk.CTkButton(self.chamada_control_frame, text="< Voltar ao Menu", command=self.show_main_menu, fg_color="transparent", border_width=1)
        self.chamada_back_button.grid(row=7, column=0, columnspan=2, padx=20, pady=(20, 10), sticky="s")

        # --- 1.3. Frame do Menu de Controle de ALUNOS (inicialmente oculto) ---
        self.alunos_control_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        # (grid é chamado em show_view)
        self.alunos_control_label = ctk.CTkLabel(self.alunos_control_frame, text="Filtros de Alunos", font=ctk.CTkFont(size=16, weight="bold"))
        self.alunos_control_label.grid(row=0, column=0, padx=20, pady=(20, 10))
        # Adicionar filtros aqui no futuro, se necessário
        self.alunos_back_button = ctk.CTkButton(self.alunos_control_frame, text="< Voltar ao Menu", command=self.show_main_menu, fg_color="transparent", border_width=1)
        self.alunos_back_button.grid(row=7, column=0, padx=20, pady=(20, 10), sticky="s")

        # --- 1.4. Frame do Menu de Controle de TURMAS (inicialmente oculto) ---
        self.turmas_control_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        # (grid é chamado em show_view)
        self.turmas_control_label = ctk.CTkLabel(self.turmas_control_frame, text="Controle de Turmas", font=ctk.CTkFont(size=16, weight="bold"))
        self.turmas_control_label.grid(row=0, column=0, padx=20, pady=(20, 10))
        self.turmas_back_button = ctk.CTkButton(self.turmas_control_frame, text="< Voltar ao Menu", command=self.show_main_menu, fg_color="transparent", border_width=1)
        self.turmas_back_button.grid(row=7, column=0, padx=20, pady=(20, 10), sticky="s")

        # --- 2. ÁREA PRINCIPAL COM ABAS ---
        self.tab_view = ctk.CTkTabview(self, corner_radius=8)
        self.tab_view.grid(row=0, column=1, padx=20, pady=20, sticky="nsew")
        self.tab_view.add("Chamada")
        self.tab_view.add("Alunos")
        self.tab_view.add("Turmas")
        self.tab_view.set("Chamada") # Aba inicial

        # --- 2.1. Conteúdo da Aba "Chamada" ---
        self.tab_view.tab("Chamada").grid_columnconfigure(0, weight=1)
        self.tab_view.tab("Chamada").grid_rowconfigure(1, weight=1)
        self.chamada_info_label = ctk.CTkLabel(self.tab_view.tab("Chamada"), text="Use o menu de controle para buscar uma turma.", font=ctk.CTkFont(size=14))
        self.chamada_info_label.grid(row=0, column=0, padx=10, pady=10)
        self.chamada_scroll_frame = ctk.CTkScrollableFrame(self.tab_view.tab("Chamada"), label_text="Lista de Chamada")
        self.chamada_scroll_frame.grid(row=1, column=0, sticky="nsew")

        # --- 2.2. Conteúdo da Aba "Alunos" ---
        self.tab_view.tab("Alunos").grid_columnconfigure(0, weight=1)
        self.tab_view.tab("Alunos").grid_rowconfigure(0, weight=1)
        self.alunos_scroll_frame = ctk.CTkScrollableFrame(self.tab_view.tab("Alunos"), label_text="Cadastro Geral de Alunos")
        self.alunos_scroll_frame.grid(row=0, column=0, sticky="nsew")

        # --- 2.3. Conteúdo da Aba "Turmas" ---
        self.tab_view.tab("Turmas").grid_columnconfigure(0, weight=1)
        self.tab_view.tab("Turmas").grid_rowconfigure(0, weight=1)
        self.turmas_scroll_frame = ctk.CTkScrollableFrame(self.tab_view.tab("Turmas"), label_text="Lista de Turmas e Atalhos")
        self.turmas_scroll_frame.grid(row=0, column=0, sticky="nsew")

        # --- ARMAZENAMENTO DE ESTADO ---
        meses = [datetime(2000, i, 1).strftime('%B') for i in range(1, 13)]
        self.mes_atual_str = meses[datetime.now().month - 1]
        self.chamada_data = {} # Guarda os dados da API
        self.chamada_widgets = {} # Guarda os widgets de botão para poder ler o estado

        # --- INICIALIZAÇÃO ---
        self.carregar_filtros_iniciais()
        self.show_main_menu() # Garante que o menu principal seja exibido no início

    def show_view(self, view_name: str):
        """Muda a aba principal e ajusta a sidebar."""
        self.tab_view.set(view_name)
        self.main_menu_frame.grid_forget()
        self.chamada_control_frame.grid_forget()
        self.alunos_control_frame.grid_forget()
        self.turmas_control_frame.grid_forget()

        if view_name == "Chamada":
            self.chamada_control_frame.grid(row=1, column=0, sticky="nsew")
        elif view_name == "Alunos":
            self.alunos_control_frame.grid(row=1, column=0, sticky="nsew")
            self.carregar_lista_alunos() # Carrega a lista ao entrar na aba
        elif view_name == "Turmas":
            self.turmas_control_frame.grid(row=1, column=0, sticky="nsew")
            self.carregar_lista_turmas() # Carrega a lista ao entrar na aba

    def show_main_menu(self):
        """Mostra o menu principal e esconde os de controle."""
        self.chamada_control_frame.grid_forget()
        self.alunos_control_frame.grid_forget()
        self.turmas_control_frame.grid_forget()
        self.main_menu_frame.grid(row=1, column=0, sticky="nsew")

    def toggle_sidebar(self):
        """Recolhe ou expande a sidebar."""
        if self.sidebar_expanded:
            # Recolher
            self.main_menu_frame.grid_forget()
            self.chamada_control_frame.grid_forget()
            self.alunos_control_frame.grid_forget()
            self.turmas_control_frame.grid_forget()

            self.sidebar_frame.configure(width=50)
            self.toggle_sidebar_button.configure(text="☰") # Manter o ícone
            self.sidebar_expanded = False
        else:
            # Expandir
            self.sidebar_frame.configure(width=250)
            self.show_view(self.tab_view.get()) # Mostra o menu de controle correto para a aba atual
            self.sidebar_expanded = True

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
                data = response.json()
                self.chamada_turma_combo.configure(values=data.get('turmas', []))
                self.chamada_turma_combo.set(data.get('turmas', [''])[0])
                self.chamada_horario_combo.configure(values=data.get('horarios', []))
                self.chamada_horario_combo.set(data.get('horarios', [''])[0])
                professores = data.get('professores', [])
                self.chamada_prof_var.set(professores[0] if professores else "")
            except requests.exceptions.RequestException as e:
                messagebox.showerror("Erro de Conexão", f"Não foi possível carregar os filtros da API.\nVerifique se o backend está rodando.\n\nErro: {e}")
        
        self.run_in_thread(_task)

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
                self.chamada_info_label.configure(text="Nenhum aluno encontrado para os filtros selecionados.")
                return

            self.chamada_info_label.configure(text=f"Exibindo {len(self.chamada_data['alunos'])} alunos.")
            self.construir_grid()

        except requests.exceptions.RequestException as e:
            self.chamada_info_label.configure(text="Erro ao buscar dados.")
            messagebox.showerror("Erro de API", f"Não foi possível buscar os dados dos alunos.\n\nErro: {e}")

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
        payload = {"registros": {}}

        if not self.chamada_widgets:
            messagebox.showwarning("Aviso", "Não há dados de chamada para salvar. Busque os alunos primeiro.")
            self.chamada_info_label.configure(text="Nada para salvar.")
            return

        # Coleta os dados dos widgets
        for nome_aluno, data_widgets in self.chamada_widgets.items():
            registros_aluno = {}
            for data_str, widget_info in data_widgets.items():
                status_id = widget_info["var"].get()
                status_code = STATUS_MAP[status_id]["code"]
                registros_aluno[data_str] = status_code
            
            if registros_aluno:
                payload["registros"][nome_aluno] = registros_aluno

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

    def carregar_lista_alunos(self):
        """Busca e exibe a lista completa de alunos na aba 'Alunos'."""
        for widget in self.alunos_scroll_frame.winfo_children():
            widget.destroy()

        try:
            response = requests.get(f"{API_BASE_URL}/api/all-alunos")
            response.raise_for_status()
            alunos = response.json()

            headers = ["Nome", "Turma", "Horário", "Professor", "Nível"]
            self.alunos_scroll_frame.grid_columnconfigure(0, weight=1)

            for i, header in enumerate(headers):
                ctk.CTkLabel(self.alunos_scroll_frame, text=header, font=ctk.CTkFont(weight="bold")).grid(row=0, column=i, padx=5, pady=2, sticky="w")

            for row_idx, aluno in enumerate(alunos, start=1):
                for col_idx, key in enumerate(headers):
                    ctk.CTkLabel(self.alunos_scroll_frame, text=aluno.get(key, ""), anchor="w").grid(row=row_idx, column=col_idx, padx=5, pady=2, sticky="ew")

        except requests.exceptions.RequestException as e:
            ctk.CTkLabel(self.alunos_scroll_frame, text=f"Erro ao carregar alunos: {e}").pack()

    def carregar_lista_turmas(self):
        """Busca e exibe a lista de turmas com botões de atalho."""
        for widget in self.turmas_scroll_frame.winfo_children():
            widget.destroy()

        try:
            response = requests.get(f"{API_BASE_URL}/api/all-turmas")
            response.raise_for_status()
            turmas = response.json()

            headers = ["Turma", "Horário", "Professor", "Qtd.", "Chamada"]
            self.turmas_scroll_frame.grid_columnconfigure(0, weight=1)
            self.turmas_scroll_frame.grid_columnconfigure(1, weight=1)
            self.turmas_scroll_frame.grid_columnconfigure(2, weight=1)

            for i, header in enumerate(headers):
                # Centraliza o cabeçalho da quantidade
                anchor = "center" if header == "Qtd." else "w"
                ctk.CTkLabel(self.turmas_scroll_frame, text=header, font=ctk.CTkFont(weight="bold"), anchor=anchor).grid(row=0, column=i, padx=5, pady=5, sticky="ew")

            for row_idx, turma in enumerate(turmas, start=1):
                ctk.CTkLabel(self.turmas_scroll_frame, text=turma.get("Turma", ""), anchor="w").grid(row=row_idx, column=0, padx=5, pady=5, sticky="ew")
                ctk.CTkLabel(self.turmas_scroll_frame, text=turma.get("Horário", ""), anchor="w").grid(row=row_idx, column=1, padx=5, pady=5, sticky="ew")
                ctk.CTkLabel(self.turmas_scroll_frame, text=turma.get("Professor", ""), anchor="w").grid(row=row_idx, column=2, padx=5, pady=5, sticky="ew")
                ctk.CTkLabel(self.turmas_scroll_frame, text=turma.get("qtd.", 0), anchor="center").grid(row=row_idx, column=3, padx=5, pady=5, sticky="ew")
                
                # Botão de atalho com ícone
                atalho_btn = ctk.CTkButton(self.turmas_scroll_frame, text="»", width=40, font=ctk.CTkFont(size=16, weight="bold"))
                atalho_btn.configure(command=lambda t=turma: self.usar_atalho_turma(t))
                atalho_btn.grid(row=row_idx, column=4, padx=5, pady=5)

        except requests.exceptions.RequestException as e:
            ctk.CTkLabel(self.turmas_scroll_frame, text=f"Erro ao carregar turmas: {e}").pack()

    def usar_atalho_turma(self, turma_info: dict):
        """Preenche os filtros e muda para a aba de chamada."""
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
