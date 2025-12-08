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
    3: {"text": "🛡️", "code": "j", "fg_color": "#F39C12", "hover_color": "#d35400"}, # Justificado
}

class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Gerenciador de Chamadas")
        self.geometry("1200x700")
        ctk.set_appearance_mode("System")

        # --- Estrutura Principal ---
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # --- Sidebar (Painel de Controle) ---
        self.sidebar_frame = ctk.CTkFrame(self, width=250, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, rowspan=4, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(6, weight=1)

        self.logo_label = ctk.CTkLabel(self.sidebar_frame, text="Controles", font=ctk.CTkFont(size=20, weight="bold"))
        self.logo_label.grid(row=0, column=0, padx=20, pady=(20, 10))

        # Filtros
        self.turma_combo = ctk.CTkComboBox(self.sidebar_frame, values=["Carregando..."])
        self.turma_combo.grid(row=1, column=0, padx=20, pady=10, sticky="ew")

        self.horario_combo = ctk.CTkComboBox(self.sidebar_frame, values=["Carregando..."])
        self.horario_combo.grid(row=2, column=0, padx=20, pady=10, sticky="ew")

        self.professor_combo = ctk.CTkComboBox(self.sidebar_frame, values=["Carregando..."])
        self.professor_combo.grid(row=3, column=0, padx=20, pady=10, sticky="ew")

        meses = [datetime(2000, i, 1).strftime('%B') for i in range(1, 13)]
        self.mes_combo = ctk.CTkComboBox(self.sidebar_frame, values=meses)
        self.mes_combo.set(meses[datetime.now().month - 1])
        self.mes_combo.grid(row=4, column=0, padx=20, pady=10, sticky="ew")

        self.buscar_button = ctk.CTkButton(self.sidebar_frame, text="Buscar Alunos", command=self.iniciar_busca_alunos)
        self.buscar_button.grid(row=5, column=0, padx=20, pady=10, sticky="ew")

        self.salvar_button = ctk.CTkButton(self.sidebar_frame, text="Salvar Alterações", command=self.iniciar_salvar_chamada, fg_color="#007bff", hover_color="#0056b3")
        self.salvar_button.grid(row=7, column=0, padx=20, pady=20, sticky="s")

        # --- Área Principal (Grid de Chamada) ---
        self.main_frame = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.main_frame.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
        self.main_frame.grid_columnconfigure(0, weight=1)
        self.main_frame.grid_rowconfigure(1, weight=1)

        self.info_label = ctk.CTkLabel(self.main_frame, text="Selecione os filtros e clique em 'Buscar Alunos'", font=ctk.CTkFont(size=14))
        self.info_label.grid(row=0, column=0, padx=10, pady=10)

        self.scrollable_frame = ctk.CTkScrollableFrame(self.main_frame, label_text="Lista de Chamada")
        self.scrollable_frame.grid(row=1, column=0, sticky="nsew")

        # Armazenamento de estado
        self.chamada_data = {} # Guarda os dados da API
        self.chamada_widgets = {} # Guarda os widgets de botão para poder ler o estado

        # Carregar filtros iniciais
        self.carregar_filtros_iniciais()

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
                self.turma_combo.configure(values=data.get('turmas', []))
                self.turma_combo.set(data.get('turmas', [''])[0])
                self.horario_combo.configure(values=data.get('horarios', []))
                self.horario_combo.set(data.get('horarios', [''])[0])
                self.professor_combo.configure(values=data.get('professores', []))
                self.professor_combo.set(data.get('professores', [''])[0])
            except requests.exceptions.RequestException as e:
                messagebox.showerror("Erro de Conexão", f"Não foi possível carregar os filtros da API.\nVerifique se o backend está rodando.\n\nErro: {e}")
        
        self.run_in_thread(_task)

    def iniciar_busca_alunos(self):
        self.info_label.configure(text="Buscando dados...")
        # Limpa o grid anterior
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        self.run_in_thread(self.buscar_e_construir_grid)

    def buscar_e_construir_grid(self):
        params = {
            "turma": self.turma_combo.get(),
            "horario": self.horario_combo.get(),
            "professor": self.professor_combo.get(),
            "mes": datetime.strptime(self.mes_combo.get(), '%B').month
        }
        try:
            response = requests.get(f"{API_BASE_URL}/api/alunos", params=params)
            response.raise_for_status()
            self.chamada_data = response.json()

            if not self.chamada_data.get('alunos'):
                self.info_label.configure(text="Nenhum aluno encontrado para os filtros selecionados.")
                return

            self.info_label.configure(text=f"Exibindo {len(self.chamada_data['alunos'])} alunos.")
            self.construir_grid()

        except requests.exceptions.RequestException as e:
            self.info_label.configure(text="Erro ao buscar dados.")
            messagebox.showerror("Erro de API", f"Não foi possível buscar os dados dos alunos.\n\nErro: {e}")

    def construir_grid(self):
        """Cria a tabela de chamada com base nos dados recebidos."""
        self.chamada_widgets = {}
        
        headers = ['Nível', 'Nome'] + [d.split('/')[0] for d in self.chamada_data['datas']]
        
        # Configura o grid dentro do scrollable frame
        self.scrollable_frame.grid_columnconfigure(1, weight=1) # Coluna do nome

        # Cria os cabeçalhos
        for i, header_text in enumerate(headers):
            header_label = ctk.CTkLabel(self.scrollable_frame, text=header_text, font=ctk.CTkFont(weight="bold"))
            header_label.grid(row=0, column=i, padx=1, pady=1, sticky="ew")

        # Cria as linhas para cada aluno
        for row_idx, aluno in enumerate(self.chamada_data['alunos'], start=1):
            nome_aluno = aluno['Nome']
            
            # Label do Nível
            nivel_label = ctk.CTkLabel(self.scrollable_frame, text=aluno['Nível'])
            nivel_label.grid(row=row_idx, column=0, padx=(5,1), pady=1)

            # Label do Nome
            nome_label = ctk.CTkLabel(self.scrollable_frame, text=nome_aluno, anchor="w")
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

                btn = ctk.CTkButton(self.scrollable_frame,
                                    text=STATUS_MAP[estado_inicial]["text"],
                                    fg_color=STATUS_MAP[estado_inicial]["fg_color"],
                                    hover_color=STATUS_MAP[estado_inicial]["hover_color"],
                                    width=40,
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
        self.info_label.configure(text="Salvando...")
        self.run_in_thread(self.salvar_chamada)

    def salvar_chamada(self):
        payload = {"registros": {}}

        if not self.chamada_widgets:
            messagebox.showwarning("Aviso", "Não há dados de chamada para salvar. Busque os alunos primeiro.")
            self.info_label.configure(text="Nada para salvar.")
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
            self.info_label.configure(text="Nenhuma alteração para salvar.")
            return

        try:
            response = requests.post(f"{API_BASE_URL}/api/chamada", json=payload)
            response.raise_for_status()
            messagebox.showinfo("Sucesso", "Chamada salva com sucesso!")
            self.info_label.configure(text="Dados salvos com sucesso!")
        except requests.exceptions.RequestException as e:
            messagebox.showerror("Erro ao Salvar", f"Não foi possível salvar os dados na API.\n\nErro: {e}")
            self.info_label.configure(text="Falha ao salvar.")


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

