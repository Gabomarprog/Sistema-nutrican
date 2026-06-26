from flask import Flask, render_template, request, redirect, url_for, session, flash, make_response
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
from datetime import datetime
import pdfkit
import os

app = Flask(__name__)
app.secret_key = "nutrican_premium_key_2026"

# FIX 1: Crear una ruta absoluta para que la base de datos funcione en Linux (Render) y Windows
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(BASE_DIR, "inventario_fifo.db")
REGISTROS_POR_PAGINA = 10

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS usuarios (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS lotes (
                    id_lote TEXT PRIMARY KEY,
                    producto TEXT NOT NULL,
                    cantidad INTEGER NOT NULL,
                    precio_unidad REAL NOT NULL,
                    fecha_ingreso TEXT NOT NULL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS movimientos (
                    id_movimiento INTEGER PRIMARY KEY AUTOINCREMENT,
                    id_usuario TEXT NOT NULL,
                    id_lote TEXT NOT NULL,
                    tipo TEXT NOT NULL,
                    categoria TEXT NOT NULL,
                    cantidad INTEGER NOT NULL,
                    precio_unidad REAL NOT NULL,
                    monto_total REAL NOT NULL,
                    fecha_hora TEXT NOT NULL,
                    descripcion TEXT)''')
    
    c.execute("SELECT * FROM usuarios WHERE username = 'Eileen'")
    if not c.fetchone():
        c.execute("INSERT INTO usuarios (username, password_hash) VALUES (?, ?)", 
                  ('Eileen', generate_password_hash('Leen123*')))
    conn.commit()
    conn.close()

# FIX 2: Ejecutar init_db globalmente. Gunicorn ignora el bloque __main__, 
# por lo que esto es obligatorio para que Render cree las tablas.
init_db()

@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("SELECT * FROM usuarios WHERE username = ?", (username,))
        user = c.fetchone()
        conn.close()
        if user and check_password_hash(user[2], password):
            session['username'] = user[1]
            return redirect(url_for('dashboard'))
        flash("Usuario o contraseña incorrectos", "error")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))

@app.route('/dashboard')
def dashboard():
    if 'username' not in session: return redirect(url_for('login'))
    
    page = int(request.args.get('page', 1))
    per_page = REGISTROS_POR_PAGINA 
    offset = (page - 1) * per_page
    
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT SUM(cantidad) FROM lotes")
    total_stock = c.fetchone()[0] or 0
    c.execute("SELECT SUM(monto_total) FROM movimientos WHERE tipo = 'Salida'")
    ventas_totales = c.fetchone()[0] or 0.0
    
    c.execute("SELECT * FROM movimientos ORDER BY fecha_hora DESC LIMIT ? OFFSET ?", (per_page, offset))
    movimientos = c.fetchall()
    
    c.execute("SELECT COUNT(*) FROM movimientos")
    total_movimientos = c.fetchone()[0]
    conn.close()
    
    total_pages = (total_movimientos + per_page - 1) // per_page
    if total_pages == 0: total_pages = 1
    
    return render_template('dashboard.html', usuario=session['username'], stock=total_stock, ventas=ventas_totales, movimientos=movimientos, page=page, total_pages=total_pages)

@app.route('/inventario')
def inventario():
    if 'username' not in session: return redirect(url_for('login'))
    
    page = int(request.args.get('page', 1))
    per_page = REGISTROS_POR_PAGINA  
    offset = (page - 1) * per_page
    
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    c.execute("SELECT SUM(cantidad) FROM lotes")
    total_stock = c.fetchone()[0] or 0
    c.execute("SELECT SUM(monto_total) FROM movimientos WHERE tipo = 'Salida'")
    ventas_totales = c.fetchone()[0] or 0.0
    
    c.execute("SELECT * FROM lotes WHERE cantidad > 0 ORDER BY fecha_ingreso ASC LIMIT ? OFFSET ?", (per_page, offset))
    lotes = c.fetchall()
    
    c.execute("SELECT COUNT(*) FROM lotes WHERE cantidad > 0")
    total_lotes = c.fetchone()[0]
    conn.close()
    
    total_pages = (total_lotes + per_page - 1) // per_page
    if total_pages == 0: total_pages = 1
    
    return render_template('inventario.html', lotes=lotes, usuario=session['username'], page=page, total_pages=total_pages, stock=total_stock, ventas=ventas_totales)

@app.route('/entradas', methods=['GET', 'POST'])
def entradas():
    if 'username' not in session: return redirect(url_for('login'))
    if request.method == 'POST':
        numero_ingresado = request.form['id_lote']
        
        meses_abrev = {
            1: 'ene', 2: 'feb', 3: 'mar', 4: 'abr', 5: 'may', 6: 'jun', 
            7: 'jul', 8: 'ago', 9: 'sep', 10: 'oct', 11: 'nov', 12: 'dic'
        }
        mes_actual = datetime.now().month
        id_lote_final = f"Lote-{meses_abrev[mes_actual]}-{numero_ingresado}"
        
        producto = request.form['producto']
        cantidad = int(request.form['cantidad'])
        precio_unidad = float(request.form['precio_unidad'])
        descripcion = request.form['descripcion']
        monto_total = cantidad * precio_unidad
        fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        try:
            c.execute("INSERT INTO lotes (id_lote, producto, cantidad, precio_unidad, fecha_ingreso) VALUES (?, ?, ?, ?, ?)",
                      (id_lote_final, producto, cantidad, precio_unidad, fecha_actual))
            
            c.execute("""INSERT INTO movimientos (id_usuario, id_lote, tipo, categoria, cantidad, precio_unidad, monto_total, fecha_hora, descripcion) 
                          VALUES (?, ?, 'Entrada', 'Abastecimiento', ?, ?, ?, ?, ?)""",
                      (session['username'], id_lote_final, cantidad, precio_unidad, monto_total, fecha_actual, descripcion))
            
            conn.commit()
            flash(f"Lote {id_lote_final} registrado.", "success")
        except sqlite3.IntegrityError:
            flash("El ID del Lote ya existe.", "error")
        finally:
            conn.close()
        return redirect(url_for('entradas'))
    return render_template('entradas.html', usuario=session['username'])

@app.route('/salidas', methods=['GET', 'POST'])
def salidas():
    if 'username' not in session: return redirect(url_for('login'))
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    if request.method == 'POST':
        id_lote = request.form['id_lote']
        cantidad_vender = int(request.form['cantidad'])
        precio_unidad = float(request.form['precio_unidad'])
        descripcion = request.form['descripcion']
        monto_total = cantidad_vender * precio_unidad
        fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute("SELECT cantidad FROM lotes WHERE id_lote = ?", (id_lote,))
        lote = c.fetchone()
        if lote and lote[0] >= cantidad_vender:
            nueva_cantidad = lote[0] - cantidad_vender
            c.execute("UPDATE lotes SET cantidad = ? WHERE id_lote = ?", (nueva_cantidad, id_lote))
            c.execute("""INSERT INTO movimientos (id_usuario, id_lote, tipo, categoria, cantidad, precio_unidad, monto_total, fecha_hora, descripcion) 
                         VALUES (?, ?, 'Salida', 'Venta', ?, ?, ?, ?, ?)""",
                      (session['username'], id_lote, cantidad_vender, precio_unidad, monto_total, fecha_actual, descripcion))
            id_factura = c.lastrowid
            conn.commit()
            conn.close()
            return redirect(url_for('ver_factura', id_factura=id_factura))
        else:
            flash("Cantidad insuficiente.", "error")
            conn.close()
            return redirect(url_for('salidas'))
    c.execute("SELECT * FROM lotes WHERE cantidad > 0 ORDER BY fecha_ingreso ASC")
    lotes_disponibles = c.fetchall()
    conn.close()
    return render_template('salidas.html', lotes=lotes_disponibles, usuario=session['username'])

@app.route('/factura/<int:id_factura>')
def ver_factura(id_factura):
    if 'username' not in session: return redirect(url_for('login'))
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""SELECT m.id_movimiento, m.fecha_hora, m.id_usuario, m.descripcion, m.cantidad, m.precio_unidad, m.monto_total, l.producto, m.id_lote 
                 FROM movimientos m JOIN lotes l ON m.id_lote = l.id_lote WHERE m.id_movimiento = ?""", (id_factura,))
    datos = c.fetchone()
    conn.close()
    if not datos: return "Factura no encontrada."
    return render_template('factura.html', f=datos)

@app.route('/procesar_devolucion', methods=['POST'])
def procesar_devolucion():
    if 'username' not in session: return redirect(url_for('login'))
    
    id_lote = request.form['id_lote']
    cantidad_devuelta = int(request.form['cantidad'])
    motivo = request.form['motivo']
    fecha_actual = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    c.execute("SELECT precio_unidad FROM lotes WHERE id_lote = ?", (id_lote,))
    lote = c.fetchone()
    
    if lote:
        precio_unidad = lote[0]
        monto_total = cantidad_devuelta * precio_unidad
        
        c.execute("UPDATE lotes SET cantidad = cantidad - ? WHERE id_lote = ?", 
                  (cantidad_devuelta, id_lote))
        
        c.execute("""INSERT INTO movimientos (id_usuario, id_lote, tipo, categoria, cantidad, precio_unidad, monto_total, fecha_hora, descripcion) 
                     VALUES (?, ?, 'Devolución', 'Devolución Lote', ?, ?, ?, ?, ?)""",
                  (session['username'], id_lote, cantidad_devuelta, precio_unidad, monto_total, fecha_actual, motivo))
        
        conn.commit()
        flash(f"Devolución procesada correctamente para {id_lote}.", "success")
    
    conn.close()
    return redirect(url_for('inventario'))

@app.route('/factura/<int:id_factura>/pdf')
def descargar_pdf(id_factura):
    if 'username' not in session: return redirect(url_for('login'))
    
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""SELECT m.id_movimiento, m.fecha_hora, m.id_usuario, m.descripcion, m.cantidad, m.precio_unidad, m.monto_total, l.producto, m.id_lote 
                 FROM movimientos m JOIN lotes l ON m.id_lote = l.id_lote WHERE m.id_movimiento = ?""", (id_factura,))
    datos = c.fetchone()
    conn.close()
    
    html = render_template('factura.html', f=datos, is_pdf=True)
    
    # FIX 3: Adaptar la ruta de wkhtmltopdf según el sistema operativo
    if os.name == 'nt':  # Si estás ejecutando en Windows (tu equipo local)
        ruta_wkhtmltopdf = r'C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe'
        config = pdfkit.configuration(wkhtmltopdf=ruta_wkhtmltopdf)
        pdf = pdfkit.from_string(html, False, configuration=config)
    else:  # Si estás en Linux (Render)
        # En Render necesitarás tener wkhtmltopdf instalado en el entorno.
        # Por ahora esto evitará el error de ruta estricta de Windows.
        pdf = pdfkit.from_string(html, False)
    
    response = make_response(pdf)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename=Factura_{id_factura}.pdf'
    return response

if __name__ == '__main__':
    app.run(debug=True, port=5000)
