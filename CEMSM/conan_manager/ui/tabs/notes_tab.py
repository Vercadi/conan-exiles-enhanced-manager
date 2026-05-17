"""Persistent per-mod notes tab."""
from __future__ import annotations

import tkinter as tk

import customtkinter as ctk

from ...core.mod_notes_store import NoteSubject

FILTERS = ["All", "In Active Load Order", "Has Notes"]


class NotesTab(ctk.CTkFrame):
    def __init__(self, master, *, app):
        super().__init__(master)
        self.app = app
        self._filter_var = ctk.StringVar(value="All")
        self._subjects: list[NoteSubject] = []
        self._selected_key: str = ""
        self._build()
        self.refresh()

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self, fg_color="#101010")
        header.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 6))
        header.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            header,
            text="Notes",
            font=self.app.ui_font("page_title"),
            text_color="#f1e7d0",
        ).grid(row=0, column=0, sticky="w")
        self._status_label = ctk.CTkLabel(
            header,
            text="",
            font=self.app.ui_font("small"),
            text_color="#b9aa92",
            anchor="w",
        )
        self._status_label.grid(row=1, column=0, sticky="ew", pady=(2, 0))

        body = ctk.CTkFrame(self, fg_color="#191715", border_width=1, border_color="#3a3028")
        body.grid(row=1, column=0, sticky="nsew", padx=10, pady=6)
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=2)
        body.grid_rowconfigure(1, weight=1)

        left_top = ctk.CTkFrame(body, fg_color="transparent")
        left_top.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 6))
        left_top.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            left_top,
            text="Mods",
            font=self.app.ui_font("card_title"),
            text_color="#f0b35f",
        ).grid(row=0, column=0, sticky="w")
        self._filter_menu = ctk.CTkOptionMenu(
            left_top,
            variable=self._filter_var,
            values=FILTERS,
            width=170,
            height=self.app.ui_tokens.compact_button_height,
            fg_color="#3a3028",
            button_color="#5d3424",
            button_hover_color="#70402c",
            font=self.app.ui_font("body"),
            command=lambda _value: self.refresh(),
        )
        self._filter_menu.grid(row=0, column=1, sticky="e")

        self._listbox = tk.Listbox(
            body,
            selectmode=tk.BROWSE,
            exportselection=False,
            bg="#101010",
            fg="#f1e7d0",
            selectbackground="#7d4429",
            selectforeground="#ffffff",
            activestyle="none",
            borderwidth=0,
            highlightthickness=0,
            font=("Cascadia Mono", self.app.ui_tokens.mono),
        )
        self._listbox.grid(row=1, column=0, sticky="nsew", padx=(10, 5), pady=(0, 10))
        self._listbox.bind("<<ListboxSelect>>", self._on_select)
        self._listbox.bind("<KeyPress>", self._jump_by_letter)

        editor = ctk.CTkFrame(body, fg_color="#101010", border_width=1, border_color="#3a3028")
        editor.grid(row=0, column=1, rowspan=2, sticky="nsew", padx=(5, 10), pady=10)
        editor.grid_columnconfigure(0, weight=1)
        editor.grid_rowconfigure(2, weight=1)
        ctk.CTkLabel(
            editor,
            text="Mod Note",
            font=self.app.ui_font("card_title"),
            text_color="#f0b35f",
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 2))
        self._detail_label = ctk.CTkLabel(
            editor,
            text="Select a mod.",
            font=self.app.ui_font("small"),
            text_color="#b9aa92",
            anchor="w",
            justify="left",
            wraplength=self.app.ui_tokens.panel_wrap,
        )
        self._detail_label.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 8))
        self._text = ctk.CTkTextbox(
            editor,
            fg_color="#0c0c0c",
            text_color="#f1e7d0",
            border_width=1,
            border_color="#3a3028",
            font=("Cascadia Mono", self.app.ui_tokens.mono),
            wrap="word",
        )
        self._text.grid(row=2, column=0, sticky="nsew", padx=10, pady=(0, 10))

        controls = ctk.CTkFrame(editor, fg_color="transparent")
        controls.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 10))
        for column in range(3):
            controls.grid_columnconfigure(column, weight=1)
        self._button(controls, "Save Note", self._save_note, column=0)
        self._button(controls, "Clear Note", self._clear_note, column=1)
        self._button(controls, "Copy Note", self._copy_note, column=2)

    def _button(self, parent, text: str, command, *, column: int) -> None:
        ctk.CTkButton(
            parent,
            text=text,
            height=self.app.ui_tokens.compact_button_height,
            font=self.app.ui_font("body"),
            fg_color="#3a3028",
            hover_color="#4a3c31",
            command=command,
        ).grid(row=0, column=column, sticky="ew", padx=(0, 8), pady=(0, 4))

    def refresh(self) -> None:
        previous = self._selected_key
        self._subjects = list(self.app.note_subjects(self._filter_var.get()))
        self._listbox.delete(0, tk.END)
        note_count = self.app.mod_notes.note_count()
        for subject in self._subjects:
            note = self.app.note_for_key(subject.key)
            note_marker = "notes" if note and note.text.strip() else "no notes"
            active_marker = "active" if subject.active else "library"
            self._listbox.insert(tk.END, f"{subject.display_name} [{active_marker}; {note_marker}; {subject.source_type}]")
        if previous:
            for index, subject in enumerate(self._subjects):
                if subject.key == previous:
                    self._listbox.selection_set(index)
                    self._listbox.see(index)
                    break
        self._status_label.configure(text=f"{len(self._subjects)} mod(s) visible, {note_count} with saved notes.")
        self._load_selected_note()

    def _on_select(self, _event=None) -> None:
        self._load_selected_note()

    def _load_selected_note(self) -> None:
        selection = self._listbox.curselection()
        if not selection or int(selection[0]) >= len(self._subjects):
            self._selected_key = ""
            self._detail_label.configure(text="Select a mod.")
            self._text.delete("1.0", tk.END)
            return
        subject = self._subjects[int(selection[0])]
        self._selected_key = subject.key
        note = self.app.note_for_key(subject.key)
        self._detail_label.configure(
            text=(
                f"{subject.display_name}\n"
                f"Source: {subject.source_type} | Key: {subject.key}"
                + (f" | Workshop ID: {subject.workshop_id}" if subject.workshop_id else "")
            )
        )
        self._text.delete("1.0", tk.END)
        if note:
            self._text.insert("1.0", note.text)

    def _selected_subject(self) -> NoteSubject | None:
        if not self._selected_key:
            return None
        for subject in self._subjects:
            if subject.key == self._selected_key:
                return subject
        return None

    def _save_note(self) -> None:
        subject = self._selected_subject()
        if subject is None:
            self.app.notify_warning("No Mod Selected", "Select a mod before saving a note.", popup=False)
            return
        self.app.save_mod_note(subject, self._text.get("1.0", tk.END).strip())

    def _clear_note(self) -> None:
        subject = self._selected_subject()
        if subject is None:
            self.app.notify_warning("No Mod Selected", "Select a mod before clearing a note.", popup=False)
            return
        self.app.clear_mod_note(subject.key)

    def _copy_note(self) -> None:
        subject = self._selected_subject()
        if subject is None:
            self.app.notify_warning("No Mod Selected", "Select a mod before copying a note.", popup=False)
            return
        text = self._text.get("1.0", tk.END).strip()
        self.clipboard_clear()
        self.clipboard_append(text)
        self.app.show_banner("success", f"Copied note for {subject.display_name}.")

    def _jump_by_letter(self, event) -> str | None:
        char = getattr(event, "char", "")
        if len(char) != 1 or not char.isalnum():
            return None
        labels = [subject.display_name for subject in self._subjects]
        current = int(self._listbox.curselection()[0]) if self._listbox.curselection() else -1
        from ...core.target_actions import next_first_letter_index

        index = next_first_letter_index(labels, char, start=current)
        if index is None:
            return None
        self._listbox.selection_clear(0, tk.END)
        self._listbox.selection_set(index)
        self._listbox.activate(index)
        self._listbox.see(index)
        self._load_selected_note()
        return "break"
