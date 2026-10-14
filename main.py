import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import sqlite3
import os
import re
from pypdf import PdfReader

DB_NAME = "examenes.db"

# ==========================================
# 1. GESTIÓN DE BASE DE DATOS
# ==========================================
def inicializar_base_datos():
    conexion = sqlite3.connect(DB_NAME)
    conexion.execute("PRAGMA foreign_keys = ON;")
    cursor = conexion.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS examenes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            archivo_origen TEXT NOT NULL,
            comenzado TEXT,
            estado TEXT,
            finalizado TEXT,
            tiempo TEXT,
            puntos TEXT,
            calificacion TEXT,
            comentario TEXT
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS preguntas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            examen_id INTEGER NOT NULL,
            enunciado TEXT NOT NULL,
            estado TEXT,
            FOREIGN KEY (examen_id) REFERENCES examenes (id) ON DELETE CASCADE
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS respuestas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pregunta_id INTEGER NOT NULL,
            respuesta TEXT NOT NULL,
            seleccionada INTEGER DEFAULT 0,
            correcta INTEGER DEFAULT 0,
            FOREIGN KEY (pregunta_id) REFERENCES preguntas (id) ON DELETE CASCADE
        )
    """)
    
    conexion.commit()
    conexion.close()

def guardar_examen_directo(datos_examen, archivo_origen):
    conexion = sqlite3.connect(DB_NAME)
    conexion.execute("PRAGMA foreign_keys = ON;")
    cursor = conexion.cursor()
    
    cursor.execute("""
        INSERT INTO examenes (archivo_origen, comenzado, estado, finalizado, tiempo, puntos, calificacion, comentario)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        archivo_origen, datos_examen['comenzado'], datos_examen['estado_examen'], datos_examen['finalizado'],
        datos_examen['tiempo'], datos_examen['puntos'], datos_examen['calificacion'],
        datos_examen['comentario']
    ))
    examen_id = cursor.lastrowid

    for p in datos_examen['preguntas']:
        cursor.execute("""
            INSERT INTO preguntas (examen_id, enunciado, estado)
            VALUES (?, ?, ?)
        """, (examen_id, p['enunciado'], p['estado']))
        pregunta_id = cursor.lastrowid
        
        for resp in p['respuestas']:
            cursor.execute("""
                INSERT INTO respuestas (pregunta_id, respuesta, seleccionada, correcta)
                VALUES (?, ?, ?, ?)
            """, (pregunta_id, resp['respuesta'], resp['seleccionada'], resp['correcta']))
            
    conexion.commit()
    conexion.close()

def obtener_estructura_completa():
    conexion = sqlite3.connect(DB_NAME)
    cursor = conexion.cursor()
    cursor.execute("SELECT id, archivo_origen, comenzado, estado, finalizado, tiempo, puntos, calificacion, comentario FROM examenes")
    examenes = cursor.fetchall()
    
    estructura = []
    for ex in examenes:
        ex_id, origen, comenzado, estado_ex, finalizado, tiempo, puntos, calif, com = ex
        cursor.execute("SELECT id, enunciado, estado FROM preguntas WHERE examen_id = ?", (ex_id,))
        preguntas = cursor.fetchall()
        
        lista_preguntas = []
        for p in preguntas:
            p_id, enunciado, estado_p = p
            cursor.execute("SELECT id, respuesta, seleccionada, correcta FROM respuestas WHERE pregunta_id = ?", (p_id,))
            respuestas = cursor.fetchall()
            lista_preguntas.append((p_id, enunciado, estado_p, respuestas))
            
        estructura.append({
            'id': ex_id, 'origen': origen, 'comenzado': comenzado, 'estado': estado_ex,
            'finalizado': finalizado, 'tiempo': tiempo, 'puntos': puntos, 'calificacion': calif,
            'comentario': com, 'preguntas': lista_preguntas
        })
        
    conexion.close()
    return estructura

def eliminar_examen_db(examen_id):
    conexion = sqlite3.connect(DB_NAME)
    conexion.execute("PRAGMA foreign_keys = ON;")
    cursor = conexion.cursor()
    cursor.execute("DELETE FROM examenes WHERE id = ?", (examen_id,))
    conexion.commit()
    conexion.close()

def eliminar_pregunta_db(pregunta_id):
    conexion = sqlite3.connect(DB_NAME)
    conexion.execute("PRAGMA foreign_keys = ON;")
    cursor = conexion.cursor()
    cursor.execute("DELETE FROM preguntas WHERE id = ?", (pregunta_id,))
    conexion.commit()
    conexion.close()

# ==========================================
# 2. PROCESADOR ROBUSTO PARA TXT FORMATEADO Y PDF
# ==========================================
def parsear_texto_comun(texto_unificado):
    def buscar_patron(patron, texto):
        m = re.search(patron, texto, re.IGNORECASE)
        return m.group(1).strip() if m else "No especificado"

    comenzado = buscar_patron(r'Comenzado el\s+(.+?)(?=\n|Estado)', texto_unificado)
    estado_examen = buscar_patron(r'Estado\s+(.+?)(?=\n|Finalizado)', texto_unificado)
    finalizado = buscar_patron(r'Finalizado en\s+(.+?)(?=\n|Tiempo)', texto_unificado)
    tiempo = buscar_patron(r'Tiempo\s+empleado\s+(.+?)(?=\n|Puntos)', texto_unificado)
    puntos = buscar_patron(r'Puntos\s+([\d,\/]+)', texto_unificado)
    calificacion = buscar_patron(r'Calificación\s+(.+?)(?=\n|Comentario)', texto_unificado)
    comentario = buscar_patron(r'Comentario\s+(.+?)(?=Pregunta\s+1|\Z)', texto_unificado)

    bloques_crudo = re.split(r'\bPregunta\s+(\d+)\b', texto_unificado)
    
    bloques_mapa = {}
    idx = 1
    while idx < len(bloques_crudo) - 1:
        try:
            num_preg = int(bloques_crudo[idx])
            contenido = bloques_crudo[idx+1]
            bloques_mapa[num_preg] = contenido
        except ValueError:
            pass
        idx += 2

    preguntas = []

    for num_p in range(1, 26):
        bloque = bloques_mapa.get(num_p, "")
        
        if not bloque.strip():
            preguntas.append({
                'enunciado': f"Pregunta {num_p} [No detectada]",
                'estado': "Incidencia de lectura",
                'respuestas': [
                    {'respuesta': 'a. [Sin opción]', 'seleccionada': 0, 'correcta': 0},
                    {'respuesta': 'b. [Sin opción]', 'seleccionada': 0, 'correcta': 0},
                    {'respuesta': 'c. [Sin opción]', 'seleccionada': 0, 'correcta': 0},
                    {'respuesta': 'd. [Sin opción]', 'seleccionada': 0, 'correcta': 0}
                ]
            })
            continue

        estado_pregunta = "Incorrecta"
        if re.search(r'\bCorrecta\b', bloque[:150], re.IGNORECASE):
            estado_pregunta = "Correcta"

        lineas = [l.strip() for l in bloque.split('\n') if l.strip()]

        lineas_enunciado = []
        lineas_respuestas = []
        capturando_respuestas = False

        for linea in lineas:
            if re.search(r'^[◉○]?\s*[a-d]\.', linea) or linea.startswith("a.") or linea.startswith("b.") or linea.startswith("c.") or linea.startswith("d."):
                capturando_respuestas = True

            es_metadato = re.match(r'^(Se puntua|Se puntúa|Correcto|Correcta|Incorrecta|Incorrecto|\d+[\.,]\d+\s+sobre\s+\d+[\.,]\d+)', linea, re.IGNORECASE)

            if not capturando_respuestas and not es_metadato:
                lineas_enunciado.append(linea)
            elif capturando_respuestas:
                lineas_respuestas.append(linea)

        enunciado = " ".join(lineas_enunciado).strip()
        if not enunciado:
            enunciado = f"Pregunta {num_p}"

        respuestas_crudas = []
        opcion_actual = ""
        for linea in lineas_respuestas:
            if re.search(r'^[◉○]?\s*[a-d]\.', linea) or linea.startswith("a.") or linea.startswith("b.") or linea.startswith("c.") or linea.startswith("d."):
                if opcion_actual:
                    respuestas_crudas.append(opcion_actual)
                opcion_actual = linea
            else:
                opcion_actual += " " + linea
        if opcion_actual:
            respuestas_crudas.append(opcion_actual)

        while len(respuestas_crudas) < 4:
            respuestas_crudas.append(f"{chr(97 + len(respuestas_crudas))}. [Sin opción detectada]")

        lista_respuestas_estructuradas = []

        for op in respuestas_crudas[:4]:
            seleccionada = 1 if ("◉" in op or "SELECCIONADA" in op.upper() or "☑" in op or "☒" in op) else 0
            es_acierto_oficial = (("" in op or "✔" in op or "CORRECTA" in op.upper()) and "INCORRECTA" not in op.upper())
            correcta = 1 if es_acierto_oficial else 0

            lista_respuestas_estructuradas.append({
                'respuesta': op,
                'seleccionada': seleccionada,
                'correcta': correcta
            })

        preguntas.append({
            'enunciado': enunciado,
            'estado': estado_pregunta,
            'respuestas': lista_respuestas_estructuradas
        })

    return {
        'comenzado': comenzado, 'estado_examen': estado_examen, 'finalizado': finalizado,
        'tiempo': tiempo, 'puntos': puntos, 'calificacion': calificacion, 'comentario': comentario,
        'preguntas': preguntas
    }

def extraer_datos_txt(ruta_txt):
    with open(ruta_txt, "r", encoding="utf-8") as f:
        texto_completo = f.read()
    return parsear_texto_comun(texto_completo)

def extraer_datos_pdf(ruta_pdf):
    lector = PdfReader(ruta_pdf)
    lineas_globales = []
    for pagina in lector.pages:
        t = pagina.extract_text()
        if t:
            for l in t.split('\n'):
                l_str = l.strip()
                if not l_str:
                    continue
                if any(l_str.startswith(x) for x in [
                    "Área personal", "Resumen de retención", "Descargar la app", 
                    "Material adicional", "Ir a...", "Resumen de retención de datos"
                ]):
                    continue
                lineas_globales.append(l_str)
    return parsear_texto_comun("\n".join(lineas_globales))

# ==========================================
# 3. INTERFAZ GRÁFICA
# ==========================================
class AppExamenes(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Gestor Integral de Exámenes - Maestro Detalle")
        self.geometry("1400x800")
        
        inicializar_base_datos()
        self.crear_interfaz()
        self.actualizar_arbol()

    def crear_interfaz(self):
        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=10, pady=10)

        # ==========================
        # PANEL IZQUIERDO (Importación y Árbol)
        # ==========================
        frame_izq = ttk.Frame(paned)
        paned.add(frame_izq, weight=1)

        btn_cargar_pdf = ttk.Button(frame_izq, text="📥 Importar Examen PDF", command=self.cargar_pdf)
        btn_cargar_pdf.pack(fill="x", padx=5, pady=3)

        btn_cargar_txt = ttk.Button(frame_izq, text="📥 Importar Examen TXT Formateado", command=self.cargar_txt)
        btn_cargar_txt.pack(fill="x", padx=5, pady=(3, 8))

        ttk.Separator(frame_izq, orient="horizontal").pack(fill="x", padx=5, pady=5)

        lbl_arbol = ttk.Label(frame_izq, text="Estructura (Examen ➔ Preguntas ➔ Respuestas)", font=("Arial", 10, "bold"))
        lbl_arbol.pack(anchor="w", padx=5, pady=2)

        self.tree = ttk.Treeview(frame_izq, selectmode="browse")
        self.tree.pack(fill="both", expand=True, padx=5, pady=5)
        self.tree.bind("<<TreeviewSelect>>", self.on_arbol_select)

        # ==========================
        # PANEL DERECHO (Búsqueda, Borrado y Detalle)
        # ==========================
        frame_der = ttk.Frame(paned)
        paned.add(frame_der, weight=2)

        # Zona de Búsqueda y Borrado colocada arriba del detalle
        frame_controles_der = ttk.LabelFrame(frame_der, text="🔍 Control y Búsqueda")
        frame_controles_der.pack(fill="x", padx=5, pady=5)

        self.entry_buscar = ttk.Entry(frame_controles_der, font=("Arial", 11))
        self.entry_buscar.pack(fill="x", padx=8, pady=5)
        self.entry_buscar.bind("<KeyRelease>", lambda e: self.actualizar_arbol())

        frame_botones_control = ttk.Frame(frame_controles_der)
        frame_botones_control.pack(fill="x", padx=8, pady=(0, 5))

        btn_restaurar = ttk.Button(frame_botones_control, text="🔄 Restaurar Búsqueda", command=self.restaurar_busqueda)
        btn_restaurar.pack(side="left", fill="x", expand=True, padx=(0, 3))

        btn_borrar = ttk.Button(frame_botones_control, text="🗑️ Borrar Seleccionado (BD)", command=self.borrar_elemento_seleccionado)
        btn_borrar.pack(side="right", fill="x", expand=True, padx=(3, 0))

        ttk.Separator(frame_der, orient="horizontal").pack(fill="x", padx=5, pady=5)

        lbl_detalle = ttk.Label(frame_der, text="Detalle del Elemento Seleccionado", font=("Arial", 11, "bold"))
        lbl_detalle.pack(anchor="w", padx=5, pady=2)

        self.txt_detalle = tk.Text(frame_der, wrap="word", font=("Arial", 11))
        self.txt_detalle.pack(fill="both", expand=True, padx=5, pady=5)
        self.txt_detalle.config(state="disabled")

        self.elementos_mapa = {}

    def cargar_pdf(self):
        ruta = filedialog.askopenfilename(filetypes=[("Archivos PDF", "*.pdf")])
        if ruta:
            try:
                nombre_archivo = os.path.basename(ruta)
                datos_examen = extraer_datos_pdf(ruta)
                if datos_examen['preguntas']:
                    guardar_examen_directo(datos_examen, nombre_archivo)
                    messagebox.showinfo("Éxito", f"Examen PDF importado correctamente.\nPreguntas guardadas: {len(datos_examen['preguntas'])}")
                    self.actualizar_arbol()
                else:
                    messagebox.showwarning("Aviso", "No se encontraron preguntas válidas en el PDF.")
            except Exception as e:
                messagebox.showerror("Error", f"Ocurrió un error al procesar el PDF:\n{str(e)}")

    def cargar_txt(self):
        ruta = filedialog.askopenfilename(filetypes=[("Archivos de Texto", "*.txt")])
        if ruta:
            try:
                nombre_archivo = os.path.basename(ruta)
                datos_examen = extraer_datos_txt(ruta)
                if datos_examen['preguntas']:
                    guardar_examen_directo(datos_examen, nombre_archivo)
                    messagebox.showinfo("Éxito", f"Examen TXT importado correctamente.\nPreguntas guardadas: {len(datos_examen['preguntas'])}")
                    self.actualizar_arbol()
                else:
                    messagebox.showwarning("Aviso", "No se encontraron preguntas válidas en el TXT.")
            except Exception as e:
                messagebox.showerror("Error", f"Ocurrió un error al procesar el TXT:\n{str(e)}")

    def restaurar_busqueda(self):
        self.entry_buscar.delete(0, tk.END)
        self.actualizar_arbol()

    def actualizar_arbol(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.elementos_mapa.clear()

        filtro = self.entry_buscar.get().strip().lower()
        examenes = obtener_estructura_completa()

        for ex in examenes:
            ex_id, origen, comenzado, estado_ex, finalizado, tiempo, puntos, calif, com, preguntas = (
                ex['id'], ex['origen'], ex['comenzado'], ex['estado'], ex['finalizado'], 
                ex['tiempo'], ex['puntos'], ex['calificacion'], ex['comentario'], ex['preguntas']
            )

            preguntas_filtradas = []
            for idx, p in enumerate(preguntas):
                p_id, enunciado, estado_p, respuestas = p
                texto_completo_p = f"p{idx+1} {enunciado} {estado_p}".lower()
                if not filtro or filtro in texto_completo_p or any(filtro in r[1].lower() for r in respuestas):
                    preguntas_filtradas.append((idx, p))

            if filtro and not preguntas_filtradas and filtro not in origen.lower():
                continue

            ex_node_id = self.tree.insert("", "end", text=f"📚 Examen: {origen}", values=("examen", ex_id))
            self.elementos_mapa[ex_node_id] = {'tipo': 'examen', 'id': ex_id, 'datos': ex}

            for idx, p in preguntas_filtradas:
                p_id, enunciado, estado_p, respuestas = p
                simbolo_p = "✅" if estado_p == "Correcta" else ("⚠️" if estado_p == "Incidencia de lectura" else "❌")
                
                p_node_id = self.tree.insert(ex_node_id, "end", text=f"{simbolo_p} P{idx+1}: {enunciado[:40]}...", values=("pregunta", p_id))
                self.elementos_mapa[p_node_id] = {'tipo': 'pregunta', 'id': p_id, 'datos': {'id': p_id, 'enunciado': enunciado, 'estado': estado_p, 'respuestas': respuestas}}

                for r_idx, r in enumerate(respuestas):
                    r_id, respuesta_texto, seleccionada, correcta = r
                    simbolo_r = "✅" if correcta else "▪"
                    r_node_id = self.tree.insert(p_node_id, "end", text=f"{simbolo_r} Opción {r_idx+1}", values=("respuesta", r_id))
                    self.elementos_mapa[r_node_id] = {'tipo': 'respuesta', 'id': r_id, 'datos': {'respuesta': respuesta_texto, 'seleccionada': seleccionada, 'correcta': correcta}}

    def on_arbol_select(self, event):
        seleccion = self.tree.selection()
        if not seleccion:
            return
        
        node_id = seleccion[0]
        elemento = self.elementos_mapa.get(node_id)
        if not elemento:
            return

        self.txt_detalle.config(state="normal")
        self.txt_detalle.delete("1.0", "end")

        tipo = elemento['tipo']
        datos = elemento['datos']

        if tipo == 'examen':
            texto = (
                f"=== DATOS DEL EXAMEN ===\n\n"
                f"• Archivo Origen: {datos['origen']}\n"
                f"• Comenzado: {datos['comenzado']}\n"
                f"• Estado: {datos['estado']}\n"
                f"• Finalizado: {datos['finalizado']}\n"
                f"• Tiempo Empleado: {datos['tiempo']}\n"
                f"• Puntos: {datos['puntos']}\n"
                f"• Calificación: {datos['calificación']}\n"
                f"• Comentario: {datos['comentario']}\n"
            )
            self.txt_detalle.insert("1.0", texto)

        elif tipo == 'pregunta':
            texto = (
                f"=== ENUNCIADO DE LA PREGUNTA ===\n\n"
                f"{datos['enunciado']}\n\n"
                f"Estado de la pregunta: {datos['estado']}\n\n"
                f"--- RESPUESTAS (4 opciones) ---\n"
            )
            for r_idx, r in enumerate(datos['respuestas']):
                _, respuesta_texto, seleccionada, correcta = r
                marca_sel = "👉 [Seleccionada]" if seleccionada else ""
                marca_cor = "✅ [Correcta oficial]" if correcta else ""
                texto += f"\n[Opción {r_idx+1}] {marca_sel} {marca_cor}\n{respuesta_texto}\n"
            self.txt_detalle.insert("1.0", texto)

        elif tipo == 'respuesta':
            sel_txt = "Sí" if datos['seleccionada'] else "No"
            cor_txt = "Sí" if datos['correcta'] else "No"
            texto = (
                f"=== DETALLE DE LA RESPUESTA ===\n\n"
                f"• Seleccionada (marca izquierda): {sel_txt}\n"
                f"• Correcta (marcas izquierda y derecha): {cor_txt}\n\n"
                f"Texto de la respuesta:\n{datos['respuesta']}\n"
            )
            self.txt_detalle.insert("1.0", texto)

        self.txt_detalle.config(state="disabled")

    def borrar_elemento_seleccionado(self):
        seleccion = self.tree.selection()
        if not seleccion:
            messagebox.showwarning("Aviso", "Por favor, selecciona un examen o una pregunta del árbol para borrar.")
            return

        node_id = seleccion[0]
        elemento = self.elementos_mapa.get(node_id)
        if not elemento:
            messagebox.showerror("Error", "No se pudo identificar el elemento seleccionado en el mapa.")
            return

        tipo = elemento['tipo']
        elem_id = elemento['id']

        if tipo == 'examen':
            if messagebox.askyesno("Confirmar Borrado", f"¿Desea borrar todo el examen y sus preguntas asociadas de la base de datos?"):
                eliminar_examen_db(elem_id)
                self.actualizar_arbol()
                self.txt_detalle.config(state="normal")
                self.txt_detalle.delete("1.0", "end")
                self.txt_detalle.config(state="disabled")
                messagebox.showinfo("Eliminado", "Examen eliminado correctamente de la base de datos.")
        elif tipo == 'pregunta':
            if messagebox.askyesno("Confirmar Borrado", "¿Desea borrar esta pregunta seleccionada de la base de datos?"):
                eliminar_pregunta_db(elem_id)
                self.actualizar_arbol()
                self.txt_detalle.config(state="normal")
                self.txt_detalle.delete("1.0", "end")
                self.txt_detalle.config(state="disabled")
                messagebox.showinfo("Eliminado", "Pregunta eliminada correctamente de la base de datos.")
        else:
            messagebox.showinfo("Información", "Para borrar respuestas individuales, por favor selecciona y borra la pregunta completa.")

if __name__ == "__main__":
    app = AppExamenes()
    app.mainloop()