from flask import Flask, render_template, redirect, url_for, request, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import os

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'clave-desarrollo-temporal-cambiar-en-produccion')

# =========================
# BASE DE DATOS
# =========================

basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'restaurante.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# =========================
# MODELOS
# =========================

class Usuario(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    nombre = db.Column(db.String(100), nullable=False)
    rol = db.Column(db.String(20), default='mesero')  # mesero, cocina, admin

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Mesa(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    numero = db.Column(db.Integer, nullable=False, unique=True)
    capacidad = db.Column(db.Integer, default=4)
    activa = db.Column(db.Boolean, default=True)

class Pedido(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.DateTime, default=datetime.now)
    mesa_id = db.Column(db.Integer, db.ForeignKey('mesa.id'), nullable=False)
    mesero_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    producto = db.Column(db.String(200), nullable=False)
    cantidad = db.Column(db.Integer, default=1)
    notas = db.Column(db.Text)
    estado = db.Column(db.String(20), default='pendiente')  # pendiente, preparando, listo, entregado
    pagado = db.Column(db.Boolean, default=False)
    
    mesa = db.relationship('Mesa', backref='pedidos')
    mesero = db.relationship('Usuario', backref='pedidos')

@login_manager.user_loader
def load_user(user_id):
    return Usuario.query.get(int(user_id))

# =========================
# RUTAS
# =========================

@app.route("/", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        
        usuario = Usuario.query.filter_by(username=username).first()
        
        if usuario and usuario.check_password(password):
            login_user(usuario)
            flash(f'Bienvenido, {usuario.nombre}!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Usuario o contraseña incorrectos', 'error')
    
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash('Sesión cerrada exitosamente', 'success')
    return redirect(url_for('login'))

@app.route("/dashboard")
@login_required
def dashboard():
    if current_user.rol == 'cocina':
        return redirect(url_for('cocina'))
    
    mesas = Mesa.query.filter_by(activa=True).order_by(Mesa.numero).all()
    
    # Obtener pedidos de hoy
    hoy = datetime.now().date()
    pedidos_hoy = Pedido.query.filter(
        db.func.date(Pedido.fecha) == hoy
    ).order_by(Pedido.fecha.desc()).all()
    
    # Agrupar por mesa
    pedidos_por_mesa = {}
    for pedido in pedidos_hoy:
        if pedido.mesa_id not in pedidos_por_mesa:
            pedidos_por_mesa[pedido.mesa_id] = {
                'mesa': pedido.mesa,
                'pedidos': [],
                'total_pendiente': 0,
                'pagado': True,
                'todos_entregados': True
            }
        pedidos_por_mesa[pedido.mesa_id]['pedidos'].append(pedido)
        if not pedido.pagado:
            pedidos_por_mesa[pedido.mesa_id]['total_pendiente'] += 1
            pedidos_por_mesa[pedido.mesa_id]['pagado'] = False
        if pedido.estado != 'entregado':
            pedidos_por_mesa[pedido.mesa_id]['todos_entregados'] = False
    
    return render_template("dashboard.html", 
                         mesas=mesas, 
                         pedidos_por_mesa=pedidos_por_mesa,
                         now=datetime.now())

@app.route("/nuevo_pedido/<int:mesa_id>", methods=["GET", "POST"])
@login_required
def nuevo_pedido(mesa_id):
    mesa = Mesa.query.get_or_404(mesa_id)
    
    if request.method == "POST":
        producto = request.form.get("producto")
        cantidad = request.form.get("cantidad", 1, type=int)
        notas = request.form.get("notas", "")
        
        pedido = Pedido(
            mesa_id=mesa_id,
            mesero_id=current_user.id,
            producto=producto,
            cantidad=cantidad,
            notas=notas
        )
        
        db.session.add(pedido)
        db.session.commit()
        
        flash(f'Pedido agregado a la Mesa {mesa.numero}', 'success')
        return redirect(url_for('ver_mesa', mesa_id=mesa_id))
    
    return render_template("nuevo_pedido.html", mesa=mesa)

@app.route("/mesa/<int:mesa_id>")
@login_required
def ver_mesa(mesa_id):
    mesa = Mesa.query.get_or_404(mesa_id)
    hoy = datetime.now().date()
    
    pedidos = Pedido.query.filter(
        Pedido.mesa_id == mesa_id,
        db.func.date(Pedido.fecha) == hoy
    ).order_by(Pedido.fecha.desc()).all()
    
    return render_template("ver_mesa.html", mesa=mesa, pedidos=pedidos, current_user=current_user)

@app.route("/cocina")
@login_required
def cocina():
    hoy = datetime.now().date()
    
    pedidos_pendientes = Pedido.query.filter(
        db.func.date(Pedido.fecha) == hoy,
        Pedido.estado.in_(['pendiente', 'preparando'])
    ).order_by(Pedido.fecha).all()
    
    return render_template("cocina.html", pedidos=pedidos_pendientes)

@app.route("/actualizar_estado/<int:pedido_id>/<estado>")
@login_required
def actualizar_estado(pedido_id, estado):
    pedido = Pedido.query.get_or_404(pedido_id)
    estados_validos = ['pendiente', 'preparando', 'listo', 'entregado']
    
    if estado in estados_validos:
        pedido.estado = estado
        db.session.commit()
        flash(f'Estado actualizado a: {estado}', 'success')
    
    return redirect(request.referrer or url_for('dashboard'))

@app.route("/marcar_pagado/<int:pedido_id>")
@login_required
def marcar_pagado(pedido_id):
    pedido = Pedido.query.get_or_404(pedido_id)
    pedido.pagado = True
    db.session.commit()
    flash('Pedido marcado como pagado', 'success')
    return redirect(request.referrer or url_for('dashboard'))

@app.route("/pagar_mesa/<int:mesa_id>")
@login_required
def pagar_mesa(mesa_id):
    hoy = datetime.now().date()
    pedidos = Pedido.query.filter(
        Pedido.mesa_id == mesa_id,
        db.func.date(Pedido.fecha) == hoy,
        Pedido.pagado == False
    ).all()
    
    for pedido in pedidos:
        pedido.pagado = True
    
    db.session.commit()
    flash(f'Todos los pedidos de la mesa {mesa_id} marcados como pagados', 'success')
    return redirect(url_for('dashboard'))

@app.route("/historial")
@login_required
def historial():
    # Obtener fecha del parámetro o usar fecha actual
    fecha_param = request.args.get('fecha')
    fecha_seleccionada = None
    
    if fecha_param:
        try:
            fecha_seleccionada = datetime.strptime(fecha_param, '%Y-%m-%d').date()
            # Obtener pedidos de la fecha seleccionada
            pedidos = Pedido.query.filter(
                db.func.date(Pedido.fecha) == fecha_seleccionada
            ).order_by(Pedido.fecha.desc()).all()
            
            pedidos_por_dia = {}
            if pedidos:
                fecha_str = fecha_seleccionada.strftime('%Y-%m-%d')
                pedidos_por_dia[fecha_str] = pedidos
        except ValueError:
            flash('Fecha inválida', 'error')
            fecha_seleccionada = None
    
    # Si no hay fecha seleccionada, mostrar últimos 7 días
    if not fecha_param or not pedidos_por_dia:
        pedidos = Pedido.query.order_by(Pedido.fecha.desc()).limit(500).all()
        
        pedidos_por_dia = {}
        for pedido in pedidos:
            fecha_str = pedido.fecha.strftime('%Y-%m-%d')
            if fecha_str not in pedidos_por_dia:
                pedidos_por_dia[fecha_str] = []
            pedidos_por_dia[fecha_str].append(pedido)
        
        # Limitar a los últimos 7 días
        pedidos_por_dia = dict(list(pedidos_por_dia.items())[:7])
    
    return render_template("historial.html", 
                         pedidos_por_dia=pedidos_por_dia,
                         fecha_seleccionada=fecha_seleccionada,
                         now=datetime.now())

@app.route("/administrar_mesas", methods=["GET", "POST"])
@login_required
def administrar_mesas():
    if current_user.rol != 'admin':
        flash('Solo los administradores pueden gestionar mesas', 'error')
        return redirect(url_for('dashboard'))
    
    if request.method == "POST":
        accion = request.form.get("accion")
        
        if accion == "agregar":
            numero = request.form.get("numero", type=int)
            capacidad = request.form.get("capacidad", type=int, default=4)
            
            if Mesa.query.filter_by(numero=numero).first():
                flash(f'La mesa {numero} ya existe', 'error')
            else:
                mesa = Mesa(numero=numero, capacidad=capacidad)
                db.session.add(mesa)
                db.session.commit()
                flash(f'Mesa {numero} agregada exitosamente', 'success')
        
        elif accion == "eliminar":
            mesa_id = request.form.get("mesa_id", type=int)
            mesa = Mesa.query.get(mesa_id)
            if mesa:
                # Verificar si tiene pedidos
                if Pedido.query.filter_by(mesa_id=mesa_id).first():
                    flash(f'No se puede eliminar la mesa {mesa.numero} porque tiene pedidos asociados', 'error')
                else:
                    db.session.delete(mesa)
                    db.session.commit()
                    flash(f'Mesa {mesa.numero} eliminada exitosamente', 'success')
        
        elif accion == "toggle":
            mesa_id = request.form.get("mesa_id", type=int)
            mesa = Mesa.query.get(mesa_id)
            if mesa:
                mesa.activa = not mesa.activa
                db.session.commit()
                estado = "activada" if mesa.activa else "desactivada"
                flash(f'Mesa {mesa.numero} {estado}', 'success')
        
        return redirect(url_for('administrar_mesas'))
    
    mesas = Mesa.query.order_by(Mesa.numero).all()
    return render_template("administrar_mesas.html", mesas=mesas)

@app.route("/administrar_usuarios", methods=["GET", "POST"])
@login_required
def administrar_usuarios():
    if current_user.rol != 'admin':
        flash('Solo los administradores pueden gestionar usuarios', 'error')
        return redirect(url_for('dashboard'))
    
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        nombre = request.form.get("nombre")
        rol = request.form.get("rol", "mesero")
        
        if Usuario.query.filter_by(username=username).first():
            flash(f'El usuario {username} ya existe', 'error')
        else:
            usuario = Usuario(username=username, nombre=nombre, rol=rol)
            usuario.set_password(password)
            db.session.add(usuario)
            db.session.commit()
            flash(f'Usuario {username} creado exitosamente', 'success')
        
        return redirect(url_for('administrar_usuarios'))
    
    usuarios = Usuario.query.order_by(Usuario.nombre).all()
    return render_template("administrar_usuarios.html", usuarios=usuarios)

@app.route("/eliminar_usuario/<int:user_id>", methods=["POST", "GET"])
@login_required
def eliminar_usuario(user_id):
    if current_user.rol != 'admin':
        flash('Solo los administradores pueden eliminar usuarios', 'error')
        return redirect(url_for('dashboard'))
    
    if user_id == current_user.id:
        flash('No puedes eliminar tu propio usuario', 'error')
        return redirect(url_for('administrar_usuarios'))
    
    usuario = Usuario.query.get_or_404(user_id)
    nombre = usuario.nombre
    db.session.delete(usuario)
    db.session.commit()
    flash(f'Usuario {nombre} eliminado', 'success')
    return redirect(url_for('administrar_usuarios'))

@app.route("/liberar_mesa/<int:mesa_id>")
@login_required
def liberar_mesa(mesa_id):
    """Marca todos los pedidos de una mesa como entregados y pagados"""
    hoy = datetime.now().date()
    pedidos = Pedido.query.filter(
        Pedido.mesa_id == mesa_id,
        db.func.date(Pedido.fecha) == hoy
    ).all()
    
    for pedido in pedidos:
        pedido.pagado = True
        pedido.estado = 'entregado'
    
    db.session.commit()
    flash(f'Mesa {mesa_id} liberada exitosamente', 'success')
    return redirect(url_for('dashboard'))

@app.route("/historial/<fecha>")
@login_required
def historial_fecha(fecha):
    """Ver historial de una fecha específica"""
    try:
        fecha_obj = datetime.strptime(fecha, '%Y-%m-%d').date()
    except ValueError:
        flash('Fecha inválida', 'error')
        return redirect(url_for('historial'))
    
    pedidos = Pedido.query.filter(
        db.func.date(Pedido.fecha) == fecha_obj
    ).order_by(Pedido.fecha.desc()).all()
    
    pedidos_por_dia = {fecha: pedidos}
    
    return render_template("historial.html", 
                         pedidos_por_dia=pedidos_por_dia,
                         fecha_seleccionada=fecha_obj)

# =========================
# INICIALIZACIÓN
# =========================

def init_db():
    with app.app_context():
        db.create_all()
        
        # Crear usuario admin si no existe
        if not Usuario.query.filter_by(username='admin').first():
            admin = Usuario(username='admin', nombre='Administrador', rol='admin')
            admin.set_password('admin123')
            db.session.add(admin)
        
        # Crear usuario mesero de prueba
        if not Usuario.query.filter_by(username='mesero1').first():
            mesero = Usuario(username='mesero1', nombre='Mesero 1', rol='mesero')
            mesero.set_password('mesero123')
            db.session.add(mesero)
        
        # Crear usuario cocina
        if not Usuario.query.filter_by(username='cocina').first():
            cocina = Usuario(username='cocina', nombre='Cocina', rol='cocina')
            cocina.set_password('cocina123')
            db.session.add(cocina)
        
        # Crear mesas si no existen
        if Mesa.query.count() == 0:
            for i in range(1, 11):
                mesa = Mesa(numero=i, capacidad=4)
                db.session.add(mesa)
        
        db.session.commit()
        print("Base de datos inicializada correctamente")

# =========================
# EJECUCIÓN
# =========================

if __name__ == "__main__":
    init_db()
    app.run(debug=True)