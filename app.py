import os, io, json, random, calendar, sqlite3
from datetime import datetime, date
from functools import wraps
from flask import Flask, render_template, request, send_file, jsonify, redirect, url_for, session
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from PyPDF2 import PdfReader, PdfWriter
import fitz  # PyMuPDF

app = Flask(__name__)
app.secret_key = "dev-key-change-me"
APP_DIR = os.path.dirname(os.path.abspath(__file__))

# diretório de uploads
UPLOAD_DIR = os.path.join(APP_DIR, "static", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# BD path
DB_PATH = os.path.join(APP_DIR, "database.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS turmas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT,
        materia TEXT
    )''')
    try:
        c.execute("ALTER TABLE turmas ADD COLUMN ano_serie TEXT")
    except sqlite3.OperationalError:
        pass
    c.execute('''CREATE TABLE IF NOT EXISTS turmas_horarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        turma_id INTEGER,
        dia_semana INTEGER, 
        horario TEXT,
        FOREIGN KEY(turma_id) REFERENCES turmas(id) ON DELETE CASCADE
    )''')
    conn.commit()
    conn.close()

init_db()

# fonte
try:
    pdfmetrics.registerFont(TTFont("Inter", os.path.join(APP_DIR, "static", "Inter-Regular.ttf")))
    BASE_FONT = "Inter"
except Exception:
    BASE_FONT = "Helvetica"

# utilitários JSON (para calibração de tabela e posições no PDF)
def load_config():
    with open(os.path.join(APP_DIR, "config.json"), "r", encoding="utf-8") as f:
        return json.load(f)

def save_config(cfg):
    with open(os.path.join(APP_DIR, "config.json"), "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

def top_to_reportlab_y(top_px, page_height):
    return page_height - top_px

def desenhar_overlay(linhas, dados_pessoais, cfg):
    page_w = cfg.get("page_width", A4[0])
    page_h = cfg.get("page_height", A4[1])
    buf = io.BytesIO()
    fs = float(cfg.get("font_size", 10))
    c = canvas.Canvas(buf, pagesize=(page_w, page_h))
    
    # 1. Desenhar Dados Pessoais (se configurados na calibração)
    if "pessoais" in cfg:
        fs_pessoal = cfg["pessoais"].get("font_size", 9)
        c.setFont(BASE_FONT, fs_pessoal)
        if "nome" in cfg["pessoais"] and dados_pessoais.get("nome"):
            px = cfg["pessoais"]["nome"][0]
            py = top_to_reportlab_y(cfg["pessoais"]["nome"][1], page_h)
            c.drawString(px, py, str(dados_pessoais["nome"]))
        
        if "cpf" in cfg["pessoais"] and dados_pessoais.get("cpf"):
            px = cfg["pessoais"]["cpf"][0]
            py = top_to_reportlab_y(cfg["pessoais"]["cpf"][1], page_h)
            c.drawString(px, py, str(dados_pessoais["cpf"]))

        if "endereco" in cfg["pessoais"] and dados_pessoais.get("endereco"):
            px = cfg["pessoais"]["endereco"][0]
            py = top_to_reportlab_y(cfg["pessoais"]["endereco"][1], page_h)
            c.drawString(px, py, str(dados_pessoais["endereco"]))

        if "telefone" in cfg["pessoais"] and dados_pessoais.get("telefone"):
            px = cfg["pessoais"]["telefone"][0]
            py = top_to_reportlab_y(cfg["pessoais"]["telefone"][1], page_h)
            c.drawString(px, py, str(dados_pessoais["telefone"]))

    # 2. Desenhar Tabela
    c.setFont(BASE_FONT, fs)
    table_cfg = cfg["table"]
    x0, top_y = table_cfg["origin_top_left"]
    
    widths = table_cfg["col_widths"]
    cols = ["data","dia_semana","horario","atividades","rubrica"]
    x_positions = [x0]
    for key in cols[:-1]:
        x_positions.append(x_positions[-1] + widths[key])

    ascent = pdfmetrics.getAscent(BASE_FONT) * fs / 1000.0
    line_height = fs * 1.2

    for i, row in enumerate(linhas):
        if i >= table_cfg.get("rows", 18):
            break
            
        # Pega o Y configurado cirurgicamente pelo clique da calibração
        if "row_y_positions" in table_cfg and i < len(table_cfg["row_y_positions"]):
            y_top_row = top_to_reportlab_y(table_cfg["row_y_positions"][i], page_h)
        else:
            y_top_row = top_to_reportlab_y(top_y, page_h) - i * table_cfg.get("row_height", 14)

        row_y = y_top_row - ascent - 2 # 2pt de margem do topo da linha

        for j, text in enumerate(row):
            col_key = cols[j]
            max_w = widths.get(col_key, 80) - 4
            if col_key == "atividades":
                words = str(text).split()
                line = ""
                dy = 0.0
                for w in words:
                    test = (line + " " + w).strip()
                    if c.stringWidth(test, BASE_FONT, fs) <= max_w:
                        line = test
                    else:
                        c.drawString(x_positions[j] + 2, row_y - dy, line)
                        line = w
                        dy += line_height
                if line:
                    c.drawString(x_positions[j] + 2, row_y - dy, line)
            else:
                c.drawString(x_positions[j] + 2, row_y, str(text))

    c.save()
    buf.seek(0)
    return buf

# === DECORATOR ADMIN ===
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("username") == "admin" and request.form.get("password") == "admin":
            session["admin_logged_in"] = True
            return redirect(url_for("admin"))
        return render_template("login.html", error="Credenciais inválidas")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("admin_logged_in", None)
    return redirect(url_for("login"))

# === ROTAS ADMIN ===

@app.route("/admin", methods=["GET"])
@login_required
def admin():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM turmas ORDER BY id DESC")
    turmas_raw = c.fetchall()
    
    turmas = []
    for t in turmas_raw:
        c.execute("SELECT * FROM turmas_horarios WHERE turma_id = ?", (t['id'],))
        horarios = c.fetchall()
        turmas.append({
            "id": t['id'],
            "nome": t['nome'],
            "materia": t['materia'],
            "ano_serie": t['ano_serie'] if 'ano_serie' in t.keys() else "",
            "horarios": [{"dia_semana": h["dia_semana"], "horario": h["horario"]} for h in horarios]
        })
    conn.close()
    return render_template("admin.html", turmas=turmas)

@app.route("/admin/turma/save", methods=["POST"])
@login_required
def admin_save_turma():
    turma_id_form = request.form.get("turma_id")
    nome = request.form.get("nome")
    materia = request.form.get("materia")
    ano_serie = request.form.get("ano_serie", "")
    dias = request.form.getlist("dia_semana[]")
    horarios = request.form.getlist("horario_texto[]")

    if not nome or not materia:
        return "Faltando dados", 400

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    if turma_id_form:
        turma_id = int(turma_id_form)
        c.execute("UPDATE turmas SET nome=?, materia=?, ano_serie=? WHERE id=?", (nome, materia, ano_serie, turma_id))
        c.execute("DELETE FROM turmas_horarios WHERE turma_id=?", (turma_id,))
    else:
        c.execute("INSERT INTO turmas (nome, materia, ano_serie) VALUES (?, ?, ?)", (nome, materia, ano_serie))
        turma_id = c.lastrowid
    
    for dia, hor in zip(dias, horarios):
        if dia.strip() != "" and hor.strip() != "":
            c.execute("INSERT INTO turmas_horarios (turma_id, dia_semana, horario) VALUES (?, ?, ?)", 
                      (turma_id, int(dia), hor.strip()))
    
    conn.commit()
    conn.close()
    return redirect(url_for("admin"))

@app.route("/admin/turma/delete/<int:id>", methods=["POST"])
@login_required
def admin_delete_turma(id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM turmas_horarios WHERE turma_id = ?", (id,))
    c.execute("DELETE FROM turmas WHERE id = ?", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for("admin"))

# API para Frontend do Monitor
@app.route("/api/turmas", methods=["GET"])
def api_turmas():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM turmas")
    turmas_db = c.fetchall()
    
    dados = []
    for t in turmas_db:
        c.execute("SELECT dia_semana, horario FROM turmas_horarios WHERE turma_id = ?", (t['id'],))
        horarios = [{"dia_semana": h["dia_semana"], "horario": h["horario"]} for h in c.fetchall()]
        dados.append({
            "id": t["id"],
            "nome": t["nome"],
            "materia": t["materia"],
            "ano_serie": t["ano_serie"] if 'ano_serie' in t.keys() else "",
            "horarios": horarios
        })
    conn.close()
    return jsonify(dados)

@app.route("/api/curriculo", methods=["GET"])
def api_curriculo():
    try:
        with open(os.path.join(APP_DIR, "curriculo.json"), "r", encoding="utf-8") as f:
            return jsonify(json.load(f))
    except Exception:
        return jsonify({})

# === ROTAS MONITOR (GERADOR) ===

@app.route("/", methods=["GET"])
def index():
    cfg = load_config()
    return render_template("index.html", cfg=cfg)

@app.route("/generate", methods=["POST"])
def generate():
    # Carregar dados pessoais
    dados_pessoais = {
        "nome": request.form.get("nome", ""),
        "cpf": request.form.get("cpf", ""),
        "endereco": request.form.get("endereco", ""),
        "telefone": request.form.get("telefone", ""),
        "turma_id": request.form.get("turma_id", ""),
        "mes_ano": request.form.get("mes_ano", "")
    }

    # As atividades chegam via JSON (array de objetos) para flexibilidade
    atividades_json = request.form.get("atividades_data")
    if not atividades_json:
         return "Nenhuma atividade selecionada.", 400
    
    try:
        atv_list = json.loads(atividades_json)
    except:
        return "JSON de atividades inválido.", 400

    cfg = load_config()
    max_rows = cfg["table"]["rows"]

    if "template" not in request.files:
        return "Envie o PDF modelo.", 400
    template = request.files["template"]

    # Montar as linhas
    linhas = []
    for reg in atv_list:
        data_str = reg.get("data", "")
        dia_semana = reg.get("dia_semana", "")
        horario = reg.get("horario", "")
        ativ_texto = reg.get("atividade", "")
        linhas.append((data_str, dia_semana, horario, ativ_texto, ""))

    overlay_buf = desenhar_overlay(linhas, dados_pessoais, cfg)

    reader = PdfReader(template)
    writer = PdfWriter()
    page0 = reader.pages[0]
    overlay_reader = PdfReader(overlay_buf)
    overlay_page = overlay_reader.pages[0]

    page0.merge_page(overlay_page)
    writer.add_page(page0)
    for i in range(1, len(reader.pages)):
        writer.add_page(reader.pages[i])

    out_buf = io.BytesIO()
    writer.write(out_buf)
    out_buf.seek(0)
    
    nome_limpo = "".join(c for c in dados_pessoais["nome"] if c.isalnum() or c in (" ", "_")).replace(" ", "_")
    filename = f"relatorio_{nome_limpo}_{dados_pessoais['mes_ano']}.pdf"
    
    is_preview = request.form.get("is_preview") == "true"
    
    return send_file(out_buf, as_attachment=not is_preview, download_name=filename, mimetype="application/pdf")

# === CALIBRAÇÃO ===

@app.route("/calibrate", methods=["GET","POST"])
@login_required
def calibrate():
    if request.method == "GET":
        return render_template("calibrate.html")
    if "template" not in request.files:
        return jsonify({"error":"Envie um PDF"}), 400
    template = request.files["template"]
    upload_path = os.path.join(UPLOAD_DIR, "model_to_calibrate.pdf")
    template.save(upload_path)
    doc = fitz.open(upload_path)
    page = doc.load_page(0)
    zoom = 150.0 / 72.0
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    img_path = os.path.join(UPLOAD_DIR, "calibrate_page.png")
    pix.save(img_path)
    page_rect = page.rect
    resp = {
        "img_url": "/static/uploads/calibrate_page.png",
        "page_width_pts": page_rect.width,
        "page_height_pts": page_rect.height,
        "img_w_px": pix.width,
        "img_h_px": pix.height,
        "scale": zoom
    }
    return jsonify(resp)

@app.route("/save-calibration", methods=["POST"])
@login_required
def save_calibration():
    data = request.get_json(force=True)
    clicks = data.get("clicks", [])
    if len(clicks) < 28:
        return jsonify({"error":"São necessários 28 cliques."}), 400

    page_w = float(data.get("page_w_pts"))
    page_h = float(data.get("page_h_pts"))
    scale = float(data.get("scale"))
    pts = [ (c["x"]/scale, c["y"]/scale) for c in clicks[:28] ]

    # 1 a 4: dados pessoais
    pt_nome, pt_cpf, pt_end, pt_tel = pts[0], pts[1], pts[2], pts[3]

    # 5: Origem da Tabela (também é o Top Y da linha 1)
    origin = pts[4]
    
    # 6 a 10: Larguras das Colunas
    x2, _ = pts[5]
    x3, _ = pts[6]
    x4, _ = pts[7]
    x5, _ = pts[8]
    x6, _ = pts[9]

    # 11 a 28 (18 clicks): Posição Y da linha separadora abaixo de cada linha textual
    # row_y_positions guarda o topo exato Y de cada uma das 18 linhas da tabela
    row_y_positions = [round(origin[1], 2)]
    for i in range(10, 28): # Até o 27 (que é o topo da 18ª linha)
        row_y_positions.append(round(pts[i][1], 2))

    data_w     = x2 - origin[0]
    dia_w      = x3 - x2
    hor_w      = x4 - x3
    atv_w      = x5 - x4
    rubrica_w  = x6 - x5

    cfg = load_config()
    cfg["page_width"]  = page_w
    cfg["page_height"] = page_h
    
    if "pessoais" not in cfg:
        cfg["pessoais"] = {}
    
    cfg["pessoais"]["nome"] = [round(pt_nome[0], 2), round(pt_nome[1], 2)]
    cfg["pessoais"]["cpf"] = [round(pt_cpf[0], 2), round(pt_cpf[1], 2)]
    cfg["pessoais"]["endereco"] = [round(pt_end[0], 2), round(pt_end[1], 2)]
    cfg["pessoais"]["telefone"] = [round(pt_tel[0], 2), round(pt_tel[1], 2)]
    cfg["pessoais"]["font_size"] = 9

    cfg["table"]["origin_top_left"] = [round(origin[0],2), round(origin[1],2)]
    cfg["table"]["row_y_positions"] = row_y_positions
    cfg["table"]["rows"] = 18
    cfg["table"]["col_widths"] = {
        "data":       round(data_w,2),
        "dia_semana": round(dia_w,2),
        "horario":    round(hor_w,2),
        "atividades": round(atv_w,2),
        "rubrica":    round(rubrica_w,2)
    }
    save_config(cfg)
    return jsonify({"ok": True, "config": cfg})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
