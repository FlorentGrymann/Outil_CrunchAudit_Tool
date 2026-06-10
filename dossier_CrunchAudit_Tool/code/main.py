import json
import threading
import tkinter as tk
from tkinter import ttk
from datetime import datetime

from routines_V9 import (
    BASE_DIR,
    RESULTS_DIR,
    CSV_FILE,
    find_all_cases,
    classify_cases,
    compare_times,
    format_result_label,
    init_csv,
    run_benchmark_case,
    apply_reference_update,
    find_comparable_cases,
    run_comparison,
    export_comparison_csv,
    load_extra_files_config,
    save_extra_files_config,
    load_export_lists,
    save_export_lists,
    get_export_files_for_case,
    update_export_list,
    get_default_export_files,
    export_all_databases,
    export_global_database,
)

# ── Status colours ──────────────────────────────────────────────────────────
STATUS_BG = {
    "green":  "#00FF7F",
    "orange": "#FF8C00",
    "red":    "#FF2020",
    "struct": "#CCCCCC",
    "missing":"#FF2020",
    "extra":  "#CC44FF",
}
STATUS_FG = {
    "green":  "#000000",
    "orange": "#000000",
    "red":    "#FFFFFF",
    "struct": "#555555",
    "missing":"#FFFFFF",
    "extra":  "#FFFFFF",
}


class App:
    def __init__(self, root):
        self.root = root
        self.root.title("CrunchAudit_Tool")
        self.root.geometry("1200x800")

        self.stop_flag     = False
        self._last_results = []

        # ── Top bar ─────────────────────────────────────────────────────
        top_frame = tk.Frame(root)
        top_frame.pack(fill="x")

        self.restart_btn = tk.Button(
            top_frame, text="Restart",
            state="normal", command=self.restart
        )
        self.restart_btn.pack(anchor="w", padx=5, pady=5)

        # ── Notebook ────────────────────────────────────────────────────
        self.notebook = ttk.Notebook(root)
        self.notebook.pack(fill="both", expand=True)

        # Tab 1 : Performance Analysis
        self.tab_bench = tk.Frame(self.notebook)
        self.notebook.add(self.tab_bench, text="  Performance Analysis  ")

        self.main_frame = tk.Frame(self.tab_bench)
        self.main_frame.pack(fill="both", expand=True)

        start_bar = tk.Frame(self.tab_bench, bd=1, relief="raised")
        start_bar.pack(fill="x", pady=2)

        self.start_btn = tk.Button(
            start_bar, text="▶  Start",
            font=("TkDefaultFont", 10, "bold"),
            bg="#4CAF50", fg="white",
            padx=20, pady=4,
            command=self.start
        )
        self.start_btn.pack(pady=4)

        self.bottom_frame = tk.Frame(self.tab_bench)
        self.bottom_frame.pack(fill="both")

        self.progress = ttk.Progressbar(self.bottom_frame, length=600)
        self.progress.pack(pady=5)

        self.log = tk.Text(self.bottom_frame, height=10)
        self.log.pack(fill="both", expand=True)

        # Tab 2 : Results Comparison
        self.tab_comp = tk.Frame(self.notebook)
        self.notebook.add(self.tab_comp, text="  Results Comparison  ")

        self._build_comparison_tab()
        self.build_ui()

        # ── Export initial des databases ────────────────────────────────
        self.log_print("=" * 60)
        self.log_print("  EXPORT INITIAL DES DATABASES")
        self.log_print("=" * 60)
        self.log_print(f" Dossier de base : {BASE_DIR}")
        self.log_print("")
        
        # Export de la database globale
        self.log_print(" Export de la database globale (CrunchDatabase)...")
        success, msg = export_global_database(log_func=self.log_print)
        if success:
            self.log_print(f"     {msg}")
        else:
            self.log_print(f"   ⚠ {msg}")
        
        self.log_print("")
        
        # Export des databases de tous les cas
        export_all_databases(log_func=self.log_print)
        
        self.log_print("")
        self.log_print(" Initialisation terminée. Prêt à l'emploi.")
        self.log_print("=" * 60)
        self.log_print("")

        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_change)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # ==================================================================
    # TAB 1 — PERFORMANCE ANALYSIS
    # ==================================================================

    def build_ui(self):
        self.cases_dict  = find_all_cases()
        self.known_cases, self.new_cases = classify_cases(self.cases_dict)

        # {case_name: BooleanVar}  – checkbox state
        self.check_vars   = {}
        # {case_name: StringVar}  – zone de texte pour les fichiers à exporter
        self.export_text_vars = {}
        self.results      = {}
        self.result_vars  = {}
        self.case_widgets = []   # checkboxes (disabled during run)

        # ── Left panel : case selection ──────────────────────────────────
        self.left_frame = tk.Frame(self.main_frame, bd=2, relief="groove")
        self.left_frame.pack(side="left", fill="both", expand=True)

        tk.Label(self.left_frame, text="Case Selection").pack()

        self.var_all = tk.BooleanVar()
        tk.Checkbutton(
            self.left_frame, text="ALL",
            variable=self.var_all, command=self.toggle_all
        ).pack(anchor="w")

        canvas = tk.Canvas(self.left_frame)
        scrollbar = ttk.Scrollbar(self.left_frame, orient="vertical", command=canvas.yview)
        self.cases_scroll_frame = tk.Frame(canvas)

        self.cases_scroll_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=self.cases_scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        if self.new_cases:
            tk.Label(self.cases_scroll_frame,
                     text="── New cases ──", fg="blue").pack(anchor="w", padx=4)
            for name in self.new_cases:
                self._add_case_row(name, is_new=True)

        if self.known_cases:
            tk.Label(self.cases_scroll_frame,
                     text="── Known cases ──", fg="gray").pack(anchor="w", padx=4)
            for name in self.known_cases:
                self._add_case_row(name, is_new=False)

        # ── Right panel : improvements ───────────────────────────────────
        self.right_frame = tk.Frame(self.main_frame, bd=2, relief="groove")
        self.right_frame.pack(side="right", fill="both", expand=True)

        tk.Label(self.right_frame, text="Improvements").pack()

        self.var_all_results = tk.BooleanVar()
        tk.Checkbutton(
            self.right_frame, text="ALL",
            variable=self.var_all_results, command=self.toggle_all_results
        ).pack(anchor="w")

        self.results_container = tk.Frame(self.right_frame)
        self.results_container.pack(fill="both", expand=True)

        self.apply_btn = tk.Button(
            self.right_frame, text="Apply changes",
            command=self.apply_changes
        )
        self.apply_btn.pack(pady=10)

        self.message_label = tk.Label(self.right_frame, text="")
        self.message_label.pack()

    # ------------------------------------------------------------------
    # Case row
    # ------------------------------------------------------------------

    def _add_case_row(self, name, is_new):
        """
        Each case row has:
          [✓] (NEW) name_of_case
              ▶ Output files  (collapsed by default)
                  Zone de texte avec les fichiers à exporter (modifiable)
                  Bouton Add pour appliquer les modifications
        """
        outer = tk.Frame(self.cases_scroll_frame, bd=1, relief="flat")
        outer.pack(anchor="w", fill="x", padx=4, pady=2)

        # ── Header row: checkbox + collapse toggle + delete ─────────────
        header = tk.Frame(outer)
        header.pack(fill="x")

        var = tk.BooleanVar()
        label_text = ("(NEW) " if is_new else "") + name
        fg_color   = "blue" if is_new else "black"

        chk = tk.Checkbutton(
            header, text=label_text, variable=var,
            fg=fg_color,
            font=("TkDefaultFont", 9, "bold" if is_new else "normal")
        )
        chk.pack(side="left", anchor="w")

        # Collapse toggle button
        collapsed_var = tk.BooleanVar(value=True)
        toggle_btn = tk.Button(header, text="▶ Output files",
                               font=("TkDefaultFont", 8), relief="flat",
                               fg="#555", cursor="hand2")
        toggle_btn.pack(side="left", padx=(8, 0))

        # Delete case button (✕)
        del_btn = tk.Button(
            header, text="✕",
            font=("TkDefaultFont", 8, "bold"),
            fg="#e74c3c", relief="flat", cursor="hand2",
            command=lambda n=name, o=outer: self._delete_case_row(n, o)
        )
        del_btn.pack(side="right", padx=4)

        # ── Collapsible body ─────────────────────────────────────────────
        body = tk.Frame(outer, padx=20)
        # body is NOT packed initially (collapsed)

        # Zone de texte pour les fichiers à exporter
        tk.Label(body, text="Files to export:", 
                 font=("TkDefaultFont", 8, "bold"), fg="#2c3e50").pack(anchor="w", pady=(4, 2))
        
        # Récupérer la liste des fichiers à exporter pour ce cas
        case_dir = self.cases_dict.get(name)
        export_files = get_export_files_for_case(name, case_dir) if case_dir else []
        export_text = ", ".join(export_files)
        
        # Zone de texte éditable
        text_var = tk.StringVar(value=export_text)
        self.export_text_vars[name] = text_var
        
        text_frame = tk.Frame(body)
        text_frame.pack(fill="x", pady=(0, 4))
        
        export_entry = tk.Text(text_frame, height=3, width=40, 
                               font=("TkDefaultFont", 8),
                               wrap=tk.WORD)
        export_entry.pack(side="left", fill="x", expand=True)
        export_entry.insert("1.0", export_text)
        
        # Scrollbar pour la zone de texte
        text_scroll = ttk.Scrollbar(text_frame, orient="vertical", command=export_entry.yview)
        text_scroll.pack(side="right", fill="y")
        export_entry.configure(yscrollcommand=text_scroll.set)
        
        # Frame pour le bouton Add et le message d'erreur
        add_frame = tk.Frame(body)
        add_frame.pack(fill="x", pady=(0, 4))
        
        err_label = tk.Label(add_frame, text="", fg="#e74c3c",
                             font=("TkDefaultFont", 7))
        err_label.pack(side="left", padx=(0, 10))
        
        # Bouton Add (grisé de base)
        add_btn = tk.Button(add_frame, text="Add", font=("TkDefaultFont", 8),
                           state="disabled", bg="#cccccc")
        add_btn.pack(side="right")
        
        # Fonction pour activer/désactiver le bouton Add
        def on_text_change(*args):
            current_text = export_entry.get("1.0", "end-1c").strip()
            if current_text != export_text:  # Si le texte a changé
                add_btn.config(state="normal", bg="#4CAF50")
            else:
                add_btn.config(state="disabled", bg="#cccccc")
        
        export_entry.bind("<<Modified>>", lambda e: (on_text_change(), export_entry.edit_modified(False)))
        
        # Référence à la zone de texte pour pouvoir la mettre à jour
        body.export_entry = export_entry
        body.name = name
        
        def _do_add(e=export_entry, n=name, btn=add_btn, el=err_label, b=body):
            new_text = e.get("1.0", "end-1c").strip()
            
            # Valider que les fichiers existent
            case_dir = self.cases_dict.get(n)
            if case_dir and new_text:
                files = [f.strip() for f in new_text.split(",") if f.strip()]
                not_found = []
                for f in files:
                    matches = list(case_dir.rglob(f))
                    if not matches:
                        not_found.append(f)
                
                if not_found:
                    el.config(text="⚠ Not found: " + ", ".join(not_found))
                    return
            
            el.config(text="")
            
            # Sauvegarder la liste
            update_export_list(n, new_text)
            
            # Mettre à jour la référence
            export_files_list = get_export_files_for_case(n, case_dir)
            export_text_updated = ", ".join(export_files_list)
            e.delete("1.0", tk.END)
            e.insert("1.0", export_text_updated)
            
            # Désactiver le bouton Add
            btn.config(state="disabled", bg="#cccccc")
            
            self.log_print(f" Export list updated for {n}")

        add_btn.config(command=_do_add)
        
        # Toggle logic
        def _toggle(b=body, cv=collapsed_var, tb=toggle_btn):
            if cv.get():
                b.pack(fill="x")
                tb.config(text="▼ Output files")
                cv.set(False)
            else:
                b.pack_forget()
                tb.config(text="▶ Output files")
                cv.set(True)

        toggle_btn.config(command=_toggle)

        self.check_vars[name]  = var
        self.case_widgets.append(chk)

    def _delete_case_row(self, name, outer_frame):
        """Remove a case from the selection list entirely."""
        outer_frame.destroy()
        self.check_vars.pop(name, None)
        self.export_text_vars.pop(name, None)
        self.case_widgets = [w for w in self.case_widgets if w.winfo_exists()]

    # ------------------------------------------------------------------
    # Controls
    # ------------------------------------------------------------------

    def restart(self):
        """Restart complet de l'application (les deux onglets)"""
        self.stop_flag = True
        
        # Sauvegarder l'onglet actif
        current_tab = self.notebook.index(self.notebook.select())
        
        # Nettoyer les widgets existants dans le Tab 1
        for widget in self.main_frame.winfo_children():
            widget.destroy()
        self.log.delete("1.0", tk.END)
        self.progress["value"] = 0
        
        self.stop_flag = False
        self.build_ui()
        self.start_btn.config(state="normal", bg="#4CAF50")
        
        # Reset comparison tab
        self._refresh_comp_list()
        for w in self.comp_results_frame.winfo_children():
            w.destroy()
        self.comp_status_label.config(text="")
        
        # Réinitialiser les résultats
        self._last_results = []
        self.results = {}
        self.result_vars = {}
        
        # Restaurer l'onglet actif
        self.notebook.select(current_tab)
        
        # Ré-exporter les databases
        self.log_print("")
        self.log_print(" Restart : vérification des databases...")
        success, msg = export_global_database(log_func=self.log_print)
        if success:
            self.log_print(f"     {msg}")
        else:
            self.log_print(f"   ⚠ {msg}")
        self.log_print("")
        
        self.log_print(" Application restarted successfully.")

    def log_print(self, msg):
        self.log.insert(tk.END, msg + "\n")
        self.log.see(tk.END)
        self.root.update()

    def log_lines(self, lines):
        for line in lines:
            self.log_print(line)

    def toggle_all(self):
        for v in self.check_vars.values():
            v.set(self.var_all.get())

    def toggle_all_results(self):
        for v in self.result_vars.values():
            v.set(self.var_all_results.get())

    def start(self):
        selected = [n for n, v in self.check_vars.items() if v.get()]
        if not selected:
            self.message_label.config(text="Please select at least one case")
            return
        for w in self.case_widgets:
            try:
                w.config(state="disabled")
            except Exception:
                pass
        self.start_btn.config(state="disabled", bg="#aaaaaa")
        self.log_print("")
        self.log_print("=" * 60)
        self.log_print(" DÉBUT DE L'ANALYSE DE PERFORMANCE")
        self.log_print(f" {len(selected)} cas sélectionné(s)")
        self.log_print("=" * 60)
        self.log_print("")
        threading.Thread(target=self.run, args=(selected,)).start()

    def run(self, selected):
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        init_csv(CSV_FILE)
        self.progress["maximum"] = len(selected)
        timestamp = datetime.now().strftime("%Y-%m-%d_%Hh%M")

        for i, case_name in enumerate(selected, start=1):
            if self.stop_flag:
                self.log_print("")
                self.log_print(" Arrêt demandé par l'utilisateur.")
                break
            
            self.log_print(f" Cas {i}/{len(selected)} : {case_name}")
            
            case_dir = self.cases_dict[case_name]
            is_new   = case_name in self.new_cases
            
            # Récupérer les fichiers à exporter depuis la zone de texte
            export_files = get_export_files_for_case(case_name, case_dir)
            
            # Filtrer pour ne garder que les fichiers supplémentaires (pas les .in)
            extra_names = [f for f in export_files if not f.endswith('.in')]

            result = run_benchmark_case(
                case_name, case_dir, timestamp,
                is_new=is_new,
                extra_names=extra_names if extra_names else None
            )
            self.log_lines(result["logs"])

            if result.get("missing_files"):
                for mf in result["missing_files"]:
                    self.log_print("⚠ File not found in \"" + case_name + "\": " + mf)
            
            # Afficher les fichiers exportés
            if result.get("exported_files"):
                self.log_print("--- Files exported for " + case_name + " ---")
                for ef in result["exported_files"]:
                    self.log_print("  ✓ " + ef)

            if result["error"] is None and not is_new:
                self.results[case_name] = (result["tA"], result["tB"])

            self.progress["value"] = i

        self.log_print("")
        self.log_print("=" * 60)
        self.log_print(" ANALYSE TERMINÉE")
        self.log_print("=" * 60)
        self.log_print("")
        
        self.display_results()

    def display_results(self):
        for widget in self.results_container.winfo_children():
            widget.destroy()
        self.result_vars.clear()
        found = False

        for case, (a, b) in self.results.items():
            if compare_times(a, b) == "plus_rapide":
                found = True
                var = tk.BooleanVar()
                tk.Checkbutton(
                    self.results_container,
                    text=format_result_label(case, a, b),
                    variable=var
                ).pack(anchor="w")
                self.result_vars[case] = var

        if not found:
            self.message_label.config(text="No performance improvement found")
        else:
            self.message_label.config(text="Select cases to update reference")

    def apply_changes(self):
        selected = [case for case, var in self.result_vars.items() if var.get()]
        if not selected:
            self.message_label.config(text="No cases selected for update")
            return
        
        self.log_print("")
        self.log_print("=" * 60)
        self.log_print(" MISE À JOUR DES RÉFÉRENCES")
        self.log_print(f" {len(selected)} cas sélectionné(s)")
        self.log_print("=" * 60)
        
        for case in selected:
            case_dir = self.cases_dict[case]
            self.log_print(f" Mise à jour de la référence pour : {case}")
            logs = apply_reference_update(case, case_dir)
            self.log_lines(logs)
        
        self.log_print("")
        self.log_print(" Mise à jour terminée")
        self.message_label.config(text="Reference updated")

    def on_close(self):
        self.log_print("")
        self.log_print(" Fermeture de l'application...")
        self.stop_flag = True
        self.root.destroy()

    # ==================================================================
    # TAB 2 — RESULTS COMPARISON
    # ==================================================================

    def _build_comparison_tab(self):

        # ── Left panel ───────────────────────────────────────────────────
        left = tk.Frame(self.tab_comp, bd=2, relief="groove", width=320)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)

        tk.Label(left, text="Results Comparison",
                 font=("TkDefaultFont", 11, "bold")).pack(pady=(8, 4))

        # Thresholds
        thresh_frame = tk.LabelFrame(left, text="Tolerance thresholds", padx=6, pady=6)
        thresh_frame.pack(fill="x", padx=8, pady=6)

        tk.Label(thresh_frame, text="● Green threshold (max):").grid(row=0, column=0, sticky="w")
        self.thresh_green_var = tk.StringVar(value="1e-9")
        tk.Entry(thresh_frame, textvariable=self.thresh_green_var, width=12).grid(
            row=0, column=1, padx=4)

        tk.Label(thresh_frame, text="● Red threshold (min):").grid(row=1, column=0, sticky="w", pady=4)
        self.thresh_red_var = tk.StringVar(value="1e-6")
        tk.Entry(thresh_frame, textvariable=self.thresh_red_var, width=12).grid(
            row=1, column=1, padx=4)

        tk.Label(thresh_frame,
                 text="● Orange: automatically between the two",
                 fg="#FF8C00", font=("TkDefaultFont", 8, "italic")
                 ).grid(row=2, column=0, columnspan=2, sticky="w")

        # Case list with checkboxes (scrollable)
        tk.Label(left, text="Available cases:").pack(anchor="w", padx=8, pady=(6, 2))

        comp_outer = tk.Frame(left)
        comp_outer.pack(fill="both", expand=True, padx=8)

        comp_canvas = tk.Canvas(comp_outer)
        comp_sb = ttk.Scrollbar(comp_outer, orient="vertical", command=comp_canvas.yview)
        self.comp_check_frame = tk.Frame(comp_canvas)

        self.comp_check_frame.bind(
            "<Configure>",
            lambda e: comp_canvas.configure(scrollregion=comp_canvas.bbox("all"))
        )

        comp_canvas.create_window((0, 0), window=self.comp_check_frame, anchor="nw")
        comp_canvas.configure(yscrollcommand=comp_sb.set)
        comp_canvas.pack(side="left", fill="both", expand=True)
        comp_sb.pack(side="right", fill="y")

        self.comp_check_vars = {}

        tk.Button(left, text="Select all",
                  command=self._comp_select_all).pack(fill="x", padx=8, pady=(4, 0))

        self.comp_btn = tk.Button(
            left, text="▶  Compare",
            font=("TkDefaultFont", 10, "bold"),
            bg="#2980b9", fg="white", pady=6,
            command=self._run_comparison
        )
        self.comp_btn.pack(fill="x", padx=8, pady=(6, 2))

        self.export_btn = tk.Button(
            left, text="  Export CSV",
            font=("TkDefaultFont", 9),
            bg="#7f8c8d", fg="white", pady=4,
            command=self._export_csv
        )
        self.export_btn.pack(fill="x", padx=8, pady=(0, 4))

        self.comp_status_label = tk.Label(left, text="", wraplength=290,
                                          font=("TkDefaultFont", 8))
        self.comp_status_label.pack(padx=8, pady=4)

        # ── Right panel : scrollable results ────────────────────────────
        right = tk.Frame(self.tab_comp, bd=2, relief="groove")
        right.pack(side="right", fill="both", expand=True)

        tk.Label(right, text="Results",
                 font=("TkDefaultFont", 11, "bold")).pack(pady=(8, 4))

        res_canvas = tk.Canvas(right)
        res_scroll = ttk.Scrollbar(right, orient="vertical", command=res_canvas.yview)
        self.comp_results_frame = tk.Frame(res_canvas)

        self.comp_results_frame.bind(
            "<Configure>",
            lambda e: res_canvas.configure(scrollregion=res_canvas.bbox("all"))
        )

        res_canvas.create_window((0, 0), window=self.comp_results_frame, anchor="nw")
        res_canvas.configure(yscrollcommand=res_scroll.set)
        res_canvas.pack(side="left", fill="both", expand=True)
        res_scroll.pack(side="right", fill="y")

        self._refresh_comp_list()

    def _on_tab_change(self, event):
        if self.notebook.index(self.notebook.select()) == 1:
            self._refresh_comp_list()

    def _refresh_comp_list(self):
        for w in self.comp_check_frame.winfo_children():
            w.destroy()
        self.comp_check_vars.clear()

        for case_name in find_comparable_cases():
            var = tk.BooleanVar()
            tk.Checkbutton(
                self.comp_check_frame,
                text=case_name, variable=var, anchor="w"
            ).pack(fill="x", anchor="w")
            self.comp_check_vars[case_name] = var

    def _comp_select_all(self):
        for v in self.comp_check_vars.values():
            v.set(True)

    def _get_thresholds(self):
        try:
            tg = float(self.thresh_green_var.get())
        except ValueError:
            tg = 1e-9
        try:
            tr = float(self.thresh_red_var.get())
        except ValueError:
            tr = 1e-6
        return tg, tr

    def _run_comparison(self):
        selected = [n for n, v in self.comp_check_vars.items() if v.get()]
        if not selected:
            self.comp_status_label.config(text="Please select at least one case.")
            return

        tg, tr = self._get_thresholds()

        for w in self.comp_results_frame.winfo_children():
            w.destroy()

        self.comp_btn.config(state="disabled", bg="#aaaaaa")
        self.comp_status_label.config(text="Comparison in progress...")
        
        self.log_print("")
        self.log_print("=" * 60)
        self.log_print(" DÉBUT DE LA COMPARAISON DES RÉSULTATS")
        self.log_print(f" {len(selected)} cas sélectionné(s)")
        self.log_print(f" Seuils : green ≤ {tg:.2e} / red ≥ {tr:.2e}")
        self.log_print("=" * 60)
        
        self.root.update()

        threading.Thread(
            target=self._comparison_worker, args=(selected, tg, tr)
        ).start()

    def _comparison_worker(self, cases, thresh_green, thresh_red):
        results = []
        for i, c in enumerate(cases, start=1):
            self.log_print(f" Comparaison {i}/{len(cases)} : {c}")
            res = run_comparison(c, thresh_green, thresh_red)
            results.append(res)
            
            # Log rapide des résultats
            for file_key, file_label in [("tabulated", "tabulated.out"),
                                          ("xyz", "proc_0Crunchfile.xyz")]:
                fdata = res["files"].get(file_key)
                if fdata is None:
                    continue
                error = fdata.get("error")
                if error:
                    self.log_print(f"   ⚠ {file_label} : {error}")
                else:
                    cols = fdata.get("columns") or []
                    worst = None
                    for col in cols:
                        if col["max_diff"] is not None:
                            if worst is None or col["max_diff"] > worst["max_diff"]:
                                worst = col
                    if worst:
                        self.log_print(f"   • {file_label} : pire delta = {worst['max_diff']:.3e} ({worst['status'].upper()})")
                    else:
                        self.log_print(f"   • {file_label} : pas de données numériques comparables")
        
        self._last_results = results
        
        self.log_print("")
        self.log_print(" Comparaison terminée")
        self.log_print("=" * 60)
        self.log_print("")
        
        self.root.after(
            0,
            lambda: self._display_comparison_results(results, thresh_green, thresh_red)
        )

    def _display_comparison_results(self, all_results, thresh_green, thresh_red):
        for w in self.comp_results_frame.winfo_children():
            w.destroy()
        for res in all_results:
            self._render_case_result(res, thresh_green, thresh_red)
        self.comp_btn.config(state="normal", bg="#2980b9")
        self.comp_status_label.config(text="Comparison complete.")

    def _render_case_result(self, res, thresh_green, thresh_red):
        case_name = res["case"]

        # Case title bar
        title_frame = tk.Frame(self.comp_results_frame, bg="#2c3e50")
        title_frame.pack(fill="x", pady=(10, 2), padx=4)
        tk.Label(
            title_frame, text="  " + case_name,
            bg="#2c3e50", fg="white",
            font=("TkDefaultFont", 10, "bold"), anchor="w"
        ).pack(fill="x", padx=4, pady=3)

        for file_label, file_key in [
            ("tabulated.out",        "tabulated"),
            ("proc_0Crunchfile.xyz", "xyz"),
        ]:
            fdata = res["files"].get(file_key)
            if fdata is None:
                continue

            file_frame = tk.LabelFrame(
                self.comp_results_frame, text=file_label, padx=6, pady=4
            )
            file_frame.pack(fill="x", padx=8, pady=4)

            error         = fdata.get("error")
            cols          = fdata.get("columns") or []
            header_issues = fdata.get("header_issues") or []

            if error:
                tk.Label(file_frame, text="⚠  " + error, fg="#e74c3c").pack(anchor="w")
                continue

            # ── Worst delta summary ──────────────────────────────────────
            worst = None
            for col in cols:
                if col["max_diff"] is not None:
                    if worst is None or col["max_diff"] > worst["max_diff"]:
                        worst = col

            if worst:
                status = worst["status"]
                bg     = STATUS_BG.get(status, "#ccc")
                fg_col = STATUS_FG.get(status, "#000")

                summary_frame = tk.Frame(file_frame, bg=bg, pady=3, padx=6)
                summary_frame.pack(fill="x", pady=(2, 4))

                # Build position text (row + col, 1-based)
                row_idx = worst.get("row_index")
                pos_txt = ""
                if row_idx is not None:
                    pos_txt = "  |  Position: row {} / col {}".format(
                        row_idx + 1, worst["col_index"] + 1
                    )

                summary_txt = (
                    "Worst delta: column \"{}\"  |  Δmax = {:.3e}{}  |  Status: {}".format(
                        worst["col_name"],
                        worst["max_diff"],
                        pos_txt,
                        status.upper()
                    )
                )

                tk.Label(
                    summary_frame, text=summary_txt,
                    bg=bg, fg=fg_col,
                    font=("TkDefaultFont", 9, "bold")
                ).pack(side="left")

                if status == "red":
                    tk.Label(
                        summary_frame,
                        text="  ⚠ Full manual check required",
                        bg=bg, fg=fg_col,
                        font=("TkDefaultFont", 9, "italic")
                    ).pack(side="left")

            else:
                tk.Label(file_frame,
                         text="No comparable numerical data.", fg="#999").pack(anchor="w")

            # ── Term check ───────────────────────────────────────────────
            hdr_frame = tk.LabelFrame(file_frame, text="Term check", padx=4, pady=4)
            hdr_frame.pack(fill="x", pady=(6, 2))

            if not header_issues:
                tk.Label(
                    hdr_frame,
                    text="  All terms present and correctly positioned",
                    fg="#27ae60",
                    font=("TkDefaultFont", 9, "bold")
                ).pack(anchor="w")
            else:
                for (idx, ref_v, test_v, statut) in header_issues:
                    if statut == "MANQUANT":
                        icon  = "X"
                        msg   = "Missing term at position {}  (expected: \"{}\")".format(
                            idx + 1, ref_v or "—")
                        color = "#c0392b"
                    elif statut == "EN_TROP":
                        icon  = "⚠"
                        msg   = "Extra term at position {}  (found: \"{}\")".format(
                            idx + 1, test_v or "—")
                        color = "#e67e22"
                    else:
                        icon  = "↔"
                        msg   = "Wrong term at position {}  (ref: \"{}\"  /  test: \"{}\")".format(
                            idx + 1, ref_v or "—", test_v or "—")
                        color = "#8e44ad"

                    tk.Label(
                        hdr_frame,
                        text="{} {}".format(icon, msg),
                        fg=color,
                        font=("TkDefaultFont", 8)
                    ).pack(anchor="w")

            # ── Threshold legend ─────────────────────────────────────────
            legend = tk.Frame(file_frame)
            legend.pack(anchor="w", pady=(6, 0))

            for lbl, st in [("● Green", "green"), ("● Orange", "orange"), ("● Red", "red")]:
                bg = STATUS_BG[st]
                fg = STATUS_FG[st]
                tk.Label(legend, text=lbl, bg=bg, fg=fg,
                         font=("TkDefaultFont", 8, "bold"),
                         padx=4, pady=1).pack(side="left", padx=3)

            tk.Label(legend,
                     text="  ≤ {:.2e}  /  {:.2e} – {:.2e}  /  ≥ {:.2e}".format(
                         thresh_green, thresh_green, thresh_red, thresh_red),
                     font=("TkDefaultFont", 7, "italic"), fg="#777"
                     ).pack(side="left")

    # ── Export CSV ───────────────────────────────────────────────────────

    def _export_csv(self):
        if not self._last_results:
            self.comp_status_label.config(
                text="No results to export. Run a comparison first.")
            return
        try:
            self.log_print(" Export CSV en cours...")
            path = export_comparison_csv(self._last_results)
            self.comp_status_label.config(text=" Exported to:\n" + str(path))
            self.log_print(f" CSV exporté : {path}")
        except Exception as e:
            self.comp_status_label.config(text="❌ Export error: " + str(e))
            self.log_print(f" Erreur export CSV : {e}")


if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()
