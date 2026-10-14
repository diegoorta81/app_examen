import base64
import os
import sqlite3
import urllib.parse
import streamlit as st
from pypdf import PdfReader, PdfWriter

# Configuración en modo ancho (Wide)
st.set_page_config(
    page_title="Gestor de Exámenes y Documentos - Intranet", page_icon="📁", layout="wide"
)

# --- INYECCIÓN DE ESTILOS CSS COMPACTOS ---
st.markdown("""
    <style>
        .block-container {
            padding-top: 1rem;
            padding-bottom: 1rem;
            padding-left: 1.5rem;
            padding-right: 1.5rem;
        }
        html, body, [class*="css"] {
            font-size: 13.5px;
        }
    </style>
""", unsafe_allow_html=True)

DB_PATH = "examenes.db"
PDF_UNIDO_NOMBRE = "documento_unido.pdf"


def conectar_db():
  if os.path.exists(DB_PATH):
    return sqlite3.connect(DB_PATH)
  return None


@st.cache_resource
def unificar_pdfs_raiz():
  """Fusiona una sola vez todos los PDFs de la carpeta raíz en un único archivo maestro."""
  archivos_pdf = [
      f
      for f in os.listdir(".")
      if f.lower().endswith(".pdf") and f != PDF_UNIDO_NOMBRE
  ]
  if not archivos_pdf:
    return None, []

  writer = PdfWriter()
  mapa_paginas = []
  pagina_actual = 1

  for archivo in sorted(archivos_pdf):
    try:
      reader = PdfReader(archivo)
      for idx, pagina in enumerate(reader.pages):
        writer.add_page(pagina)
        mapa_paginas.append({
            "pagina_global": pagina_actual,
            "documento_original": archivo,
            "pagina_original": idx + 1,
            "texto_pagina": pagina.extract_text() or "",
        })
        pagina_actual += 1
    except Exception:
      pass

  with open(PDF_UNIDO_NOMBRE, "wb") as f_out:
    writer.write(f_out)

  return PDF_UNIDO_NOMBRE, mapa_paginas


# Cargar o unificar PDFs al iniciar
pdf_maestro, mapa_paginas_global = unificar_pdfs_raiz()


# --- NAVEGACIÓN PRINCIPAL (SELECTOR DE VISTA ESTABILIZADO) ---
st.title("🗂️ Intranet de Gestión y Documentación")

modo_vista = st.radio(
    "Selecciona la sección de trabajo:",
    [
        "📚 Búsqueda sobre Textos (Base de Datos Exámenes)",
        "📄 Visor y Buscador de Documentos PDF (Carpeta Raíz / Unificado)",
    ],
    horizontal=True,
)

st.markdown("---")


# =====================================================================
# SECCIÓN 1: GESTOR DE EXÁMENES (BASE DE DATOS CON ÁRBOL PERMANENTE)
# =====================================================================
if modo_vista.startswith("📚"):
  conn = conectar_db()
  
  col_id_ex, col_desc_ex = "id", "id"
  col_id_pr, cols_texto_pr, col_fk_ex, col_inc_pr = "id", [], None, None
  col_id_rs, col_text_rs, col_fk_pr, col_bool_rs = "id", "texto", None, None
  lista_examenes = []

  if conn:
    cursor = conn.cursor()
    try:
      # Analizar tabla examenes y descubrir su columna de descripción/título real
      cursor.execute("PRAGMA table_info(examenes);")
      info_ex = cursor.fetchall()
      if info_ex:
        nombres_ex = [col[1] for col in info_ex]
        col_id_ex = nombres_ex[0]
        col_desc_ex = nombres_ex[1] if len(nombres_ex) > 1 else nombres_ex[0]
        for c in ["titulo", "nombre", "descripcion", "codigo", "examen", "asunto"]:
          if c in nombres_ex:
            col_desc_ex = c
            break
    except Exception:
      pass

    try:
      # Analizar tabla preguntas
      cursor.execute("PRAGMA table_info(preguntas);")
      info_pr = cursor.fetchall()
      if info_pr:
        nombres_pr = [col[1] for col in info_pr]
        col_id_pr = nombres_pr[0]
        cols_texto_pr = [col[1] for col in info_pr if col[2].upper() in ["TEXT", "VARCHAR", "CHAR", "STRING"] or col[1] in ["enunciado", "texto", "pregunta", "descripcion", "cuestion"]]
        if not cols_texto_pr:
          cols_texto_pr = [nombres_pr[1]] if len(nombres_pr) > 1 else [nombres_pr[0]]

        for c in nombres_pr:
          if "examen" in c.lower() or c.lower() in ["id_examen", "examen_id", "examenes_id"]:
            col_fk_ex = c
            break
        if "incidencia" in nombres_pr:
          col_inc_pr = "incidencia"
    except Exception:
      pass

    try:
      # Analizar tabla respuestas
      cursor.execute("PRAGMA table_info(respuestas);")
      info_rs = cursor.fetchall()
      if info_rs:
        nombres_rs = [col[1] for col in info_rs]
        col_id_rs = nombres_rs[0]
        for c in ["texto", "respuesta", "opcion", "descripcion"]:
          if c in nombres_rs:
            col_text_rs = c
            break
        for c in nombres_rs:
          if "pregunta" in c.lower() or c.lower() in ["id_pregunta", "pregunta_id"]:
            col_fk_pr = c
            break
        for c in nombres_rs:
          if "correcta" in c.lower() or "valida" in c.lower():
            col_bool_rs = c
            break
    except Exception:
      pass

    try:
      cursor.execute(f"SELECT {col_id_ex}, {col_desc_ex} FROM examenes")
      lista_examenes = cursor.fetchall()
    except Exception:
      lista_examenes = []
    conn.close()

  if not conn:
    st.error(f"⚠️ No se ha encontrado la base de datos '{DB_PATH}' en el directorio.")
  else:
    if "busqueda_input" not in st.session_state:
      st.session_state["busqueda_input"] = ""
    if "pregunta_activa_db" not in st.session_state:
      st.session_state["pregunta_activa_db"] = None

    def limpiar_busqueda_db():
      st.session_state["busqueda_input"] = ""
      st.session_state["pregunta_activa_db"] = None
      if "input_busqueda_widget" in st.session_state:
        st.session_state["input_busqueda_widget"] = ""

    # --- BARRA LATERAL: ÁRBOL DE NAVEGACIÓN PERMANENTE ---
    st.sidebar.subheader("📖 Navegación por Exámenes")

    if lista_examenes:
      examenes_map = {f"📖 [{row[0]}] {row[1]}": row[0] for row in lista_examenes}
      examen_sel_nombre = st.sidebar.selectbox(
          "Seleccionar Examen", list(examenes_map.keys())
      )
      examen_id = examenes_map[examen_sel_nombre]

      st.sidebar.markdown("---")
      st.sidebar.subheader("Preguntas del Examen")

      preguntas = []
      try:
        conn_p = conectar_db()
        if conn_p:
          cur_p = conn_p.cursor()
          if col_fk_ex:
            cur_p.execute(
                f"SELECT p.{col_id_pr}, p.{cols_texto_pr[0]} FROM preguntas p WHERE p.{col_fk_ex} = ?",
                (examen_id,),
            )
            preguntas = cur_p.fetchall()
          else:
            cur_p.execute(f"SELECT p.{col_id_pr}, p.{cols_texto_pr[0]} FROM preguntas p")
            preguntas = cur_p.fetchall()
          conn_p.close()
      except Exception:
        pass

      if preguntas:
        preguntas_map = {
            f"❓ P.#{p[0]}: {str(p[1])[:25]}...": p[0] for p in preguntas
        }
        pregunta_sel_label = st.sidebar.radio(
            "Selecciona una pregunta:",
            options=list(preguntas_map.keys()),
            label_visibility="collapsed",
        )
        # Actualizar pregunta activa mediante el árbol lateral
        if not st.session_state.get("clic_desde_tabla", False):
          st.session_state["pregunta_activa_db"] = preguntas_map[pregunta_sel_label]
        else:
          st.session_state["clic_desde_tabla"] = False
      else:
        st.sidebar.info("Este examen no contiene preguntas.")
    else:
      st.sidebar.warning("No hay exámenes en la base de datos.")

    st.sidebar.markdown("---")
    st.sidebar.subheader("🔍 Búsqueda Global")
    busqueda_global = st.sidebar.text_input(
        "Buscar texto en preguntas:",
        value=st.session_state["busqueda_input"],
        placeholder="Término a buscar...",
        key="input_busqueda_widget",
    )
    st.session_state["busqueda_input"] = busqueda_global
    st.sidebar.button("🔄 Restaurar búsqueda", on_click=limpiar_busqueda_db)

    modo_busq_db = bool(st.session_state["busqueda_input"].strip())

    # Panel principal: Si hay búsqueda activa, mostrar tabla de coincidencias
    if modo_busq_db:
      st.subheader(f"📊 Resultados de búsqueda para: *'{st.session_state['busqueda_input']}'*")
      try:
        conn_b = conectar_db()
        if conn_b:
          cur_b = conn_b.cursor()
          termino = f"%{st.session_state['busqueda_input']}%"

          condiciones = " OR ".join([f"p.{col} LIKE ?" for col in cols_texto_pr])
          parametros = [termino] * len(cols_texto_pr)

          if col_fk_ex:
            query_busq = f"""
                SELECT p.{col_id_pr}, p.{cols_texto_pr[0]}, e.{col_desc_ex} 
                FROM preguntas p 
                JOIN examenes e ON p.{col_fk_ex} = e.{col_id_ex} 
                WHERE {condiciones}
            """
          else:
            query_busq = f"""
                SELECT p.{col_id_pr}, p.{cols_texto_pr[0]}, 'General' 
                FROM preguntas p 
                WHERE {condiciones}
            """

          cur_b.execute(query_busq, tuple(parametros))
          resultados_tabla = cur_b.fetchall()
          conn_b.close()

          if resultados_tabla:
            st.success(f"Se han encontrado **{len(resultados_tabla)}** coincidencias.")
            
            for idx, row in enumerate(resultados_tabla):
              p_id = row[0]
              p_texto = str(row[1]) if row[1] else ""
              e_titulo = row[2]

              with st.container():
                col_i1, col_i2, col_btn = st.columns([2, 3, 1])
                with col_i1:
                  st.markdown(f"📖 **Examen:** {e_titulo}")
                  st.markdown(f"❓ **Pregunta #{p_id}**")
                with col_i2:
                  st.caption("Extracto:")
                  st.markdown(f"*{p_texto[:140]}...*")
                with col_btn:
                  if st.button(f"Ver detalle ➔", key=f"btn_db_loc_{idx}"):
                    st.session_state["pregunta_activa_db"] = p_id
                    st.session_state["clic_desde_tabla"] = True
                    st.rerun()
                st.markdown("---")
          else:
            st.warning("No se ha encontrado ninguna coincidencia con ese término.")
      except Exception as e:
        st.error(f"Error en la búsqueda de base de datos: {e}")

    # Visualizador de Detalle de la Pregunta Activa
    pregunta_id_activa = st.session_state["pregunta_activa_db"]

    if pregunta_id_activa:
      st.markdown("---")
      st.subheader(f"🖥️ Detalle de la Pregunta #{pregunta_id_activa}")
      try:
        conn_det = conectar_db()
        if conn_det:
          cur_det = conn_det.cursor()
          campos_sel = f"p.{cols_texto_pr[0]}"
          if col_inc_pr:
            campos_sel += f", p.{col_inc_pr}"

          cur_det.execute(
              f"SELECT {campos_sel} FROM preguntas p WHERE p.{col_id_pr} = ?",
              (pregunta_id_activa,),
          )
          datos_p = cur_det.fetchone()

          enunciado = datos_p[0] if datos_p else "No disponible"
          incidencia = (
              datos_p[1] if col_inc_pr and datos_p and len(datos_p) > 1 else None
          )

          respuestas = []
          if col_fk_pr:
            cols_r = f"r.{col_text_rs}"
            if col_bool_rs:
              cols_r += f", r.{col_bool_rs}"
            cur_det.execute(
                f"SELECT {cols_r} FROM respuestas r WHERE r.{col_fk_pr} = ?",
                (pregunta_id_activa,),
            )
            respuestas = cur_det.fetchall()
          conn_det.close()
        else:
          enunciado, incidencia, respuestas = "Error de conexión", None, []
      except Exception as e:
        enunciado, incidencia, respuestas = f"Error al cargar: {e}", None, []

      with st.container():
        if incidencia:
          st.warning(f"⚠️ **Incidencia registrada:** {incidencia}")

        st.info(enunciado)
        st.markdown("#### Opciones de Respuesta")

        if respuestas:
          for idx, row_r in enumerate(respuestas, 1):
            r_texto = row_r[0]
            es_correcta = row_r[1] if col_bool_rs and len(row_r) > 1 else False

            if es_correcta:
              st.success(f"**Opción {idx} (Correcta):** {r_texto}")
            else:
              st.markdown(f"**Opción {idx}:** {r_texto}")
        else:
          st.caption("No hay respuestas registradas para esta pregunta.")
    else:
      st.info("👈 Selecciona un elemento en el árbol de la izquierda para visualizar su detalle.")


# =====================================================================
# SECCIÓN 2: VISOR Y BUSCADOR DE DOCUMENTOS PDF (CARPETA RAÍZ / UNIFICADO)
# =====================================================================
else:
  archivos_pdf_originales = [
      f
      for f in os.listdir(".")
      if f.lower().endswith(".pdf") and f != PDF_UNIDO_NOMBRE
  ]

  if not pdf_maestro:
    st.warning("⚠️ No se ha encontrado ningún archivo PDF en la carpeta raíz del proyecto.")
  else:
    if "pagina_activa_unida" not in st.session_state:
      st.session_state["pagina_activa_unida"] = 1
    if "termino_buscado_pdf" not in st.session_state:
      st.session_state["termino_buscado_pdf"] = ""

    col_vis1, col_vis2 = st.columns([1, 1])

    with col_vis1:
      opciones_visor = ["📄 [Maestro] Documento Unificado Global"] + [
          f"📁 {f}" for f in archivos_pdf_originales
      ]
      seleccion_doc = st.selectbox("Seleccionar origen a visualizar:", opciones_visor)

    with col_vis2:
      busqueda_pdf_unido = st.text_input(
          "🔍 Buscar texto en el documento unificado:",
          placeholder="Escribe palabra clave...",
          value=st.session_state["termino_buscado_pdf"],
      )
      st.session_state["termino_buscado_pdf"] = busqueda_pdf_unido

    st.markdown("---")

    if busqueda_pdf_unido.strip():
      st.subheader(f"📊 Resultados de búsqueda para: *'{busqueda_pdf_unido}'*")

      tabla_resultados = []
      for item in mapa_paginas_global:
        texto_pag = item["texto_pagina"]
        if busqueda_pdf_unido.lower() in texto_pag.lower():
          parrafos = texto_pag.split("\n")
          bloque_encontrado = ""
          for p_idx, parrafo in enumerate(parrafos):
            if busqueda_pdf_unido.lower() in parrafo.lower():
              inicio_bloque = max(0, p_idx - 1)
              fin_bloque = min(len(parrafos), p_idx + 4)
              bloque_encontrado = " ".join([
                  parrafos[i].strip()
                  for i in range(inicio_bloque, fin_bloque)
                  if parrafos[i].strip()
              ])
              break

          if not bloque_encontrado:
            bloque_encontrado = texto_pag[:300] + "..."

          tabla_resultados.append({
              "Pág. Unido": item["pagina_global"],
              "Origen": item["documento_original"],
              "Pág. Orig.": item["pagina_original"],
              "BloqueTexto": bloque_encontrado,
          })

      if tabla_resultados:
        st.success(f"Se han encontrado **{len(tabla_resultados)}** coincidencias.")

        for idx, res in enumerate(tabla_resultados):
          with st.container():
            col_info1, col_info2, col_info3, col_btn = st.columns(
                [1.5, 2, 1, 2]
            )
            with col_info1:
              st.markdown(f"➡️ **Pág. Unido: {res['Pág. Unido']}**")
            with col_info2:
              st.markdown(f"📁 `{res['Origen']}`")
            with col_info3:
              st.markdown(f"Orig: {res['Pág. Orig.']}")
            with col_btn:
              if st.button(f"Ver en visor ➔", key=f"btn_unido_pdf_{idx}"):
                st.session_state["pagina_activa_unida"] = res["Pág. Unido"]
                st.rerun()

            st.text_area(
                label=f"Bloque detectado (Resultado {idx + 1})",
                value=res["BloqueTexto"],
                height=80,
                key=f"txtarea_res_pdf_{idx}",
                disabled=True,
            )
            st.markdown("---")
      else:
        st.warning("No se ha encontrado ninguna coincidencia con ese término.")

    try:
      if seleccion_doc.startswith("📄"):
        archivo_a_mostrar = pdf_maestro
        pag_param = f"#page={st.session_state['pagina_activa_unida']}"
        if st.session_state["termino_buscado_pdf"].strip():
          termino_codificado = urllib.parse.quote(
              st.session_state["termino_buscado_pdf"]
          )
          pag_param += f"&search={termino_codificado}"
      else:
        archivo_a_mostrar = seleccion_doc.replace("📁 ", "").strip()
        pag_param = "#page=1"

      with open(archivo_a_mostrar, "rb") as f:
        base64_pdf = base64.b64encode(f.read()).decode("utf-8")

      st.markdown(f"📌 **Visualizando:** `{archivo_a_mostrar}`")

      pdf_display = (
          f'<iframe src="data:application/pdf;base64,{base64_pdf}{pag_param}"'
          ' width="100%" height="750px" type="application/pdf"></iframe>'
      )
      st.markdown(pdf_display, unsafe_allow_html=True)
    except Exception as e:
      st.error(f"Error al cargar el visor PDF estilo Adobe: {e}")