"""
Assistente de configuração da box — interface gráfica simples pra quem
está instalando não precisar editar variável de ambiente nem abrir
terminal. Coleta a chave da loja (resolve o store_id sozinho, via
GET /v1/edge/whoami — o dashboard nunca mostrou o store_id como algo
copiável, só a chave), os dados do DVR, e uma ou mais câmeras (id
copiado do dashboard + canal no DVR), testa a conexão de cada uma antes
de salvar, e grava tudo em box_config.json — que config.py já sabe
carregar (ver load_box_config/ACTIVE_STORE).

Não pede ajuste fino de zona de interesse/threshold de propósito — isso
fica pra calibração manual depois (ver edge_detection_calibration na
memória do projeto); aqui o objetivo é só destravar a instalação básica.
"""

import json
import os
import threading
import tkinter as tk
from tkinter import messagebox, ttk

import requests

from capture import test_source
from config import BOX_CONFIG_PATH, build_intelbras_rtsp_url

DEFAULT_API_BASE_URL = "https://api.vigialoja.com.br"

_OK_COLOR = "#0a7d2c"
_ERROR_COLOR = "#c0392b"
_MUTED_COLOR = "#666666"


class SetupWizard(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("VigIA — Configuração da box")
        self.geometry("560x520")
        self.resizable(False, False)

        self.api_base_url = DEFAULT_API_BASE_URL
        self.api_key = ""
        self.store_id = None
        self.store_name = None
        self.dvr = {}
        self.cameras = []  # [{"camera_id", "label", "channel"}, ...]

        self._container = ttk.Frame(self, padding=20)
        self._container.pack(fill="both", expand=True)

        self._show_step_store_key()

    def _clear(self):
        for widget in self._container.winfo_children():
            widget.destroy()

    def _labeled_entry(self, parent, label, row, default="", show=None):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=4)
        entry = ttk.Entry(parent, width=42, show=show or "")
        entry.grid(row=row, column=1, sticky="w", padx=(10, 0))
        entry.insert(0, default)
        return entry

    # --- Passo 1: chave da loja -------------------------------------------

    def _show_step_store_key(self):
        self._clear()
        ttk.Label(self._container, text="Passo 1 de 3 — Chave da loja", font=("", 13, "bold")).pack(anchor="w")
        ttk.Label(
            self._container,
            text="Cole a chave da loja, mostrada no dashboard quando a loja foi cadastrada.",
            wraplength=500, justify="left",
        ).pack(anchor="w", pady=(8, 12))

        self._key_entry = ttk.Entry(self._container, width=60)
        self._key_entry.pack(anchor="w")
        self._key_entry.insert(0, self.api_key)

        self._key_status = ttk.Label(self._container, text="", foreground=_MUTED_COLOR)
        self._key_status.pack(anchor="w", pady=(10, 0))

        self._key_next_holder = ttk.Frame(self._container)
        self._key_next_holder.pack(anchor="w")

        btns = ttk.Frame(self._container)
        btns.pack(anchor="w", pady=(16, 0))
        self._verify_btn = ttk.Button(btns, text="Verificar chave", command=self._verify_key)
        self._verify_btn.pack(side="left")

    def _verify_key(self):
        key = self._key_entry.get().strip()
        if not key:
            self._key_status.config(text="Cole a chave antes de verificar.", foreground=_ERROR_COLOR)
            return

        self._verify_btn.config(state="disabled")
        self._key_status.config(text="Verificando…", foreground=_MUTED_COLOR)

        def worker():
            try:
                resp = requests.get(
                    f"{self.api_base_url}/v1/edge/whoami",
                    headers={"X-API-Key": key}, timeout=10,
                )
                if resp.status_code == 401:
                    self.after(0, self._on_key_invalid)
                    return
                resp.raise_for_status()
                data = resp.json()
                self.after(0, lambda: self._on_key_valid(key, data))
            except requests.RequestException as exc:
                self.after(0, lambda: self._on_key_error(str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _on_key_invalid(self):
        self._verify_btn.config(state="normal")
        self._key_status.config(text="Chave inválida — confira e tente de novo.", foreground=_ERROR_COLOR)

    def _on_key_error(self, message):
        self._verify_btn.config(state="normal")
        self._key_status.config(text=f"Não foi possível conectar: {message}", foreground=_ERROR_COLOR)

    def _on_key_valid(self, key, data):
        self.api_key = key
        self.store_id = data["store_id"]
        self.store_name = data["store_name"]
        self._verify_btn.config(state="normal")
        self._key_status.config(text=f"✓ Loja encontrada: {self.store_name}", foreground=_OK_COLOR)

        for widget in self._key_next_holder.winfo_children():
            widget.destroy()
        ttk.Button(self._key_next_holder, text="Avançar →", command=self._show_step_dvr).pack(pady=(10, 0), anchor="w")

    # --- Passo 2: dados do DVR ---------------------------------------------

    def _show_step_dvr(self):
        self._clear()
        ttk.Label(
            self._container, text=f"Passo 2 de 3 — Dados do DVR ({self.store_name})", font=("", 13, "bold")
        ).pack(anchor="w")
        ttk.Label(
            self._container,
            text="Os mesmos dados usados no aplicativo/app do DVR: endereço IP, usuário e senha.",
            wraplength=500, justify="left",
        ).pack(anchor="w", pady=(8, 12))

        form = ttk.Frame(self._container)
        form.pack(anchor="w", fill="x")
        self._dvr_host = self._labeled_entry(form, "Endereço IP do DVR", 0, default=self.dvr.get("host", ""))
        self._dvr_port = self._labeled_entry(form, "Porta (padrão 554)", 1, default=str(self.dvr.get("port", 554)))
        self._dvr_user = self._labeled_entry(form, "Usuário", 2, default=self.dvr.get("username", "admin"))
        self._dvr_pass = self._labeled_entry(form, "Senha", 3, default=self.dvr.get("password", ""), show="*")

        self._sub_stream_var = tk.BooleanVar(value=self.dvr.get("sub_stream", True))
        ttk.Checkbutton(
            self._container,
            text="Usar sub-stream (recomendado — mais leve pra box sem placa de vídeo)",
            variable=self._sub_stream_var,
        ).pack(anchor="w", pady=(12, 0))

        btns = ttk.Frame(self._container)
        btns.pack(anchor="w", pady=(20, 0))
        ttk.Button(btns, text="← Voltar", command=self._show_step_store_key).pack(side="left")
        ttk.Button(btns, text="Avançar →", command=self._save_dvr_and_continue).pack(side="left", padx=(8, 0))

    def _save_dvr_and_continue(self):
        host = self._dvr_host.get().strip()
        port_raw = self._dvr_port.get().strip() or "554"
        user = self._dvr_user.get().strip()
        password = self._dvr_pass.get()

        if not host or not user:
            messagebox.showerror("Dados incompletos", "Preencha ao menos o endereço IP e o usuário do DVR.")
            return
        try:
            port = int(port_raw)
        except ValueError:
            messagebox.showerror("Porta inválida", "A porta precisa ser um número (ex: 554).")
            return

        self.dvr = {
            "host": host, "port": port, "username": user, "password": password,
            "sub_stream": self._sub_stream_var.get(),
        }
        self._show_step_cameras()

    # --- Passo 3: câmeras ---------------------------------------------------

    def _show_step_cameras(self):
        self._clear()
        ttk.Label(self._container, text="Passo 3 de 3 — Câmeras", font=("", 13, "bold")).pack(anchor="w")
        ttk.Label(
            self._container,
            text='Adicione cada câmera já cadastrada no dashboard (aba "Câmeras") — cole o ID mostrado '
                 'lá e escolha o canal correspondente no DVR.',
            wraplength=500, justify="left",
        ).pack(anchor="w", pady=(8, 12))

        form = ttk.Frame(self._container)
        form.pack(anchor="w", fill="x")
        self._cam_id_entry = self._labeled_entry(form, "ID da câmera (do dashboard)", 0)
        self._cam_label_entry = self._labeled_entry(form, "Rótulo (ex: Corredor 2)", 1)
        self._cam_channel_entry = self._labeled_entry(form, "Canal no DVR", 2, default="1")

        self._cam_status = ttk.Label(self._container, text="", foreground=_MUTED_COLOR)
        self._cam_status.pack(anchor="w", pady=(6, 0))

        add_row = ttk.Frame(self._container)
        add_row.pack(anchor="w", pady=(8, 12))
        self._add_cam_btn = ttk.Button(add_row, text="Adicionar câmera", command=self._add_camera)
        self._add_cam_btn.pack(side="left")

        self._cam_list = tk.Listbox(self._container, width=72, height=6)
        self._cam_list.pack(anchor="w")
        for cam in self.cameras:
            self._cam_list.insert("end", self._camera_list_line(cam))

        ttk.Button(self._container, text="Remover selecionada", command=self._remove_selected_camera).pack(
            anchor="w", pady=(6, 0)
        )

        btns = ttk.Frame(self._container)
        btns.pack(anchor="w", pady=(20, 0))
        ttk.Button(btns, text="← Voltar", command=self._show_step_dvr).pack(side="left")
        ttk.Button(btns, text="Testar conexões", command=self._test_all_cameras).pack(side="left", padx=(8, 0))
        ttk.Button(btns, text="Salvar e concluir", command=self._save_and_finish).pack(side="left", padx=(8, 0))

    @staticmethod
    def _camera_list_line(cam):
        return f"{cam['label']} — canal {cam['channel']} — {cam['camera_id'][:8]}…"

    def _add_camera(self):
        camera_id = self._cam_id_entry.get().strip()
        label = self._cam_label_entry.get().strip()
        channel_raw = self._cam_channel_entry.get().strip()

        if not camera_id or not label:
            self._cam_status.config(text="Preencha o ID e o rótulo da câmera.", foreground=_ERROR_COLOR)
            return
        try:
            channel = int(channel_raw)
        except ValueError:
            self._cam_status.config(text="Canal precisa ser um número.", foreground=_ERROR_COLOR)
            return

        self._add_cam_btn.config(state="disabled")
        self._cam_status.config(text="Verificando câmera…", foreground=_MUTED_COLOR)

        def worker():
            try:
                # Reaproveita o endpoint de vizinhança (já autenticado por
                # X-API-Key) só pra confirmar que esse camera_id existe
                # de fato nesta loja — 404 = id errado/de outra loja.
                resp = requests.get(
                    f"{self.api_base_url}/v1/stores/{self.store_id}/cameras/{camera_id}/neighbor-ids",
                    headers={"X-API-Key": self.api_key}, timeout=10,
                )
                if resp.status_code == 404:
                    self.after(0, self._on_camera_invalid)
                    return
                resp.raise_for_status()
                self.after(0, lambda: self._on_camera_valid(camera_id, label, channel))
            except requests.RequestException as exc:
                self.after(0, lambda: self._on_camera_error(str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _on_camera_invalid(self):
        self._add_cam_btn.config(state="normal")
        self._cam_status.config(
            text="Câmera não encontrada nesta loja — confira o ID copiado do dashboard.", foreground=_ERROR_COLOR
        )

    def _on_camera_error(self, message):
        self._add_cam_btn.config(state="normal")
        self._cam_status.config(text=f"Não foi possível verificar: {message}", foreground=_ERROR_COLOR)

    def _on_camera_valid(self, camera_id, label, channel):
        cam = {"camera_id": camera_id, "label": label, "channel": channel}
        self.cameras.append(cam)
        self._cam_list.insert("end", self._camera_list_line(cam))
        self._cam_id_entry.delete(0, "end")
        self._cam_label_entry.delete(0, "end")
        self._add_cam_btn.config(state="normal")
        self._cam_status.config(text="✓ Câmera adicionada.", foreground=_OK_COLOR)

    def _remove_selected_camera(self):
        selection = self._cam_list.curselection()
        if not selection:
            return
        index = selection[0]
        self._cam_list.delete(index)
        del self.cameras[index]

    def _test_all_cameras(self):
        if not self.cameras:
            messagebox.showinfo("Nenhuma câmera", "Adicione ao menos uma câmera antes de testar.")
            return

        self._cam_status.config(
            text="Testando conexões (pode levar alguns segundos por câmera)…", foreground=_MUTED_COLOR
        )

        def worker():
            results = []
            for cam in self.cameras:
                url = build_intelbras_rtsp_url(
                    host=self.dvr["host"], username=self.dvr["username"], password=self.dvr["password"],
                    channel=cam["channel"], port=self.dvr.get("port", 554),
                    main_stream=not self.dvr.get("sub_stream", True),
                )
                ok, message = test_source(url)
                results.append((cam["label"], ok, message))
            self.after(0, lambda: self._on_test_results(results))

        threading.Thread(target=worker, daemon=True).start()

    def _on_test_results(self, results):
        self._cam_status.config(text="Teste concluído — veja o resultado.", foreground=_MUTED_COLOR)
        lines = [f"{'✓' if ok else '✗'} {label}: {message}" for label, ok, message in results]
        messagebox.showinfo("Resultado do teste", "\n".join(lines))

    def _save_and_finish(self):
        if not self.cameras:
            messagebox.showerror("Nenhuma câmera", "Adicione ao menos uma câmera antes de salvar.")
            return

        config = {
            "store_id": self.store_id,
            "store_name": self.store_name,
            "api_base_url": self.api_base_url,
            "api_key": self.api_key,
            "dvr": self.dvr,
            "cameras": self.cameras,
        }
        with open(BOX_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

        messagebox.showinfo(
            "Configuração salva",
            f"Configuração salva em {os.path.abspath(BOX_CONFIG_PATH)}.\n\n"
            "Pode fechar esta janela e iniciar a detecção normalmente.",
        )
        self.destroy()


if __name__ == "__main__":
    SetupWizard().mainloop()
