from flask import Flask, render_template, redirect, url_for, request, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta, date
import os
import json
from sqlalchemy.exc import OperationalError
from dotenv import load_dotenv

# Cargar .env en desarrollo si existe
if os.path.exists('.env'):
    load_dotenv('.env')

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'clave-desarrollo-temporal-cambiar-en-produccion')

# =========================
# BASE DE DATOS
# =========================

basedir = os.path.abspath(os.path.dirname(__file__))
# Preferir DATABASE_URL (Railway / Heroku). Si viene con `postgres://`, reemplazar por `postgresql://` para SQLAlchemy.
database_url = os.environ.get('DATABASE_URL')
if database_url:
    database_url = database_url.replace('postgres://', 'postgresql://')
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'restaurante.db')

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# Opciones para evitar errores de conexión en entornos PaaS
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {'pool_pre_ping': True} 

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

class Sesion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    mesa_id = db.Column(db.Integer, db.ForeignKey('mesa.id'), nullable=False)
    fecha_inicio = db.Column(db.DateTime, default=datetime.now)
    fecha_fin = db.Column(db.DateTime, nullable=True)
    total = db.Column(db.Float, default=0)  # NUEVO CAMPO para guardar el total
    activa = db.Column(db.Boolean, default=True)
    
    mesa = db.relationship('Mesa', backref='sesiones')
    pedidos = db.relationship('Pedido', backref='sesion', lazy='select')

class Pedido(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.DateTime, default=datetime.now)
    mesa_id = db.Column(db.Integer, db.ForeignKey('mesa.id'), nullable=False)
    sesion_id = db.Column(db.Integer, db.ForeignKey('sesion.id'), nullable=True)
    mesero_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    producto = db.Column(db.String(200), nullable=False)
    cantidad = db.Column(db.Integer, default=1)
    precio_unitario = db.Column(db.Float, default=0)  # NUEVO CAMPO
    notas = db.Column(db.Text)
    estado = db.Column(db.String(20), default='pendiente')  # pendiente, preparando, listo, entregado
    pagado = db.Column(db.Boolean, default=False)
    # Timestamp cuando se actualizó el estado por última vez
    estado_actualizado = db.Column(db.DateTime, default=datetime.now)
    
    mesa = db.relationship('Mesa', backref='pedidos')
    mesero = db.relationship('Usuario', backref='pedidos')
    
    @property
    def total(self):
        """Calcula el total del pedido"""
        return self.cantidad * self.precio_unitario

class CategoriaMenu(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    orden = db.Column(db.Integer, default=0)
    activa = db.Column(db.Boolean, default=True)
    
    items = db.relationship('ItemMenu', backref='categoria', lazy='select', cascade='all, delete-orphan')

class ItemMenu(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(200), nullable=False)
    descripcion = db.Column(db.Text)
    precio = db.Column(db.Float, nullable=False)
    categoria_id = db.Column(db.Integer, db.ForeignKey('categoria_menu.id'), nullable=False)
    disponible = db.Column(db.Boolean, default=True)
    imagen_url = db.Column(db.String(500))
    orden = db.Column(db.Integer, default=0)

@login_manager.user_loader
def load_user(user_id):
    return Usuario.query.get(int(user_id))

# Modelo para Factura (agregar con los otros modelos)
class Factura(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    numero_consecutivo = db.Column(db.String(50), unique=True, nullable=False)
    sesion_id = db.Column(db.Integer, db.ForeignKey('sesion.id'), nullable=True)
    subtotal = db.Column(db.Float, default=0)
    iva = db.Column(db.Float, default=0)
    propina = db.Column(db.Float, default=0)
    total = db.Column(db.Float, default=0)
    metodo_pago = db.Column(db.String(50), default='efectivo')
    desglose_pago = db.Column(db.Text)
    cliente_nombre = db.Column(db.String(200))
    cliente_documento = db.Column(db.String(50))
    notas = db.Column(db.Text)
    
    # ========== NUEVOS CAMPOS PARA CUENTAS POR COBRAR ==========
    estado_pago = db.Column(db.String(20), default='pagada')  # pagada, pendiente, vencida
    fecha_vencimiento = db.Column(db.Date, nullable=True)  # Cuándo debe pagar el cliente
    fecha_pago_real = db.Column(db.DateTime, nullable=True)  # Cuándo pagó realmente
    saldo_pendiente = db.Column(db.Float, default=0)  # Si pagó parcialmente
    fecha_emision = db.Column(db.DateTime, default=datetime.now)
    
    sesion = db.relationship('Sesion', backref='facturas')

# Modelo para configuración del restaurante (agregar con los otros modelos)
class ConfiguracionRestaurante(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(200), default='Mi Restaurante')
    nit = db.Column(db.String(50), default='900.000.000-0')
    direccion = db.Column(db.String(300), default='Calle 123 #45-67')
    ciudad = db.Column(db.String(100), default='Zarzal, Valle del Cauca')
    telefono = db.Column(db.String(50), default='(+57) 300 000 0000')
    email = db.Column(db.String(100))
    regimen = db.Column(db.String(100), default='Régimen Simplificado')
    resolucion_dian = db.Column(db.String(200))
    rango_facturacion = db.Column(db.String(100))
    iva_porcentaje = db.Column(db.Float, default=19.0)
    logo_url = db.Column(db.String(500))

class Presupuesto(db.Model):
    """
    RAZÓN: Define límites de gasto por categoría y período.
    Permite alertas automáticas cuando se supera el presupuesto.
    """
    id = db.Column(db.Integer, primary_key=True)
    categoria_id = db.Column(db.Integer, db.ForeignKey('categoria_gasto.id'), nullable=False)
    monto_limite = db.Column(db.Float, nullable=False)  # Límite de gasto
    periodo = db.Column(db.String(20), default='mensual')  # mensual, semanal, anual
    mes = db.Column(db.Integer, nullable=True)  # 1-12 para identificar el mes
    anio = db.Column(db.Integer, nullable=True)  # 2026, 2027, etc.
    activo = db.Column(db.Boolean, default=True)
    fecha_creacion = db.Column(db.DateTime, default=datetime.now)
    
    # Alertas
    alerta_porcentaje = db.Column(db.Integer, default=80)  # Alertar al 80%
    
    categoria = db.relationship('CategoriaGasto', backref='presupuestos')
    
    @property
    def gasto_actual(self):
        """Calcula cuánto se ha gastado en esta categoría en el período"""
        from datetime import date
        
        if self.periodo == 'mensual' and self.mes and self.anio:
            # Primer y último día del mes
            fecha_inicio = date(self.anio, self.mes, 1)
            if self.mes == 12:
                fecha_fin = date(self.anio + 1, 1, 1)
            else:
                fecha_fin = date(self.anio, self.mes + 1, 1)
            
            # Sumar gastos del mes
            total = db.session.query(
                db.func.sum(Gasto.monto)
            ).filter(
                Gasto.categoria_id == self.categoria_id,
                Gasto.fecha >= fecha_inicio,
                Gasto.fecha < fecha_fin
            ).scalar() or 0
            
            return float(total)
        
        return 0
    
    @property
    def porcentaje_usado(self):
        """Porcentaje del presupuesto que se ha usado"""
        if self.monto_limite > 0:
            return (self.gasto_actual / self.monto_limite) * 100
        return 0
    
    @property
    def disponible(self):
        """Cuánto dinero queda disponible"""
        return self.monto_limite - self.gasto_actual
    
    @property
    def estado(self):
        """Estado del presupuesto: normal, alerta, excedido"""
        porcentaje = self.porcentaje_usado
        if porcentaje >= 100:
            return 'excedido'
        elif porcentaje >= self.alerta_porcentaje:
            return 'alerta'
        else:
            return 'normal'

# AGREGAR ESTOS MODELOS DESPUÉS DE LA CLASE ConfiguracionRestaurante

class CategoriaGasto(db.Model):
    """
    RAZÓN: Organizar los gastos por categorías facilita el análisis.
    Ejemplo: "Ingredientes", "Salarios", "Servicios", "Mantenimiento"
    """
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    descripcion = db.Column(db.Text)
    color = db.Column(db.String(7), default='#6c757d')  # Color hex para visualización
    activa = db.Column(db.Boolean, default=True)
    
    # Relación: Una categoría puede tener muchos gastos
    gastos = db.relationship('Gasto', backref='categoria', lazy='select')


class Proveedor(db.Model):
    """
    RAZÓN: Registrar proveedores permite:
    - Autocompletar datos al crear gastos
    - Analizar qué proveedor es más usado
    - Llevar control de contactos
    """
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(200), nullable=False)
    nit = db.Column(db.String(50))
    telefono = db.Column(db.String(50))
    email = db.Column(db.String(100))
    direccion = db.Column(db.String(300))
    notas = db.Column(db.Text)
    activo = db.Column(db.Boolean, default=True)
    fecha_registro = db.Column(db.DateTime, default=datetime.now)
    
    # Relación: Un proveedor puede tener muchos gastos
    gastos = db.relationship('Gasto', backref='proveedor', lazy='select')


class Gasto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    
    # Información básica del gasto (YA EXISTE)
    fecha = db.Column(db.DateTime, default=datetime.now, nullable=False)
    concepto = db.Column(db.String(300), nullable=False)
    monto = db.Column(db.Float, nullable=False)
    
    # Relaciones con otras tablas (YA EXISTE)
    categoria_id = db.Column(db.Integer, db.ForeignKey('categoria_gasto.id'), nullable=False)
    proveedor_id = db.Column(db.Integer, db.ForeignKey('proveedor.id'), nullable=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    
    # Información adicional (YA EXISTE)
    metodo_pago = db.Column(db.String(50), default='efectivo')
    numero_factura = db.Column(db.String(100))
    notas = db.Column(db.Text)
    archivo_adjunto = db.Column(db.String(500))
    
    # Control (YA EXISTE)
    aprobado = db.Column(db.Boolean, default=True)
    fecha_aprobacion = db.Column(db.DateTime)
    aprobado_por_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=True)
    
    # ========== NUEVOS CAMPOS PARA CUENTAS POR PAGAR ==========
    estado_pago = db.Column(db.String(20), default='pagado')  # pagado, pendiente, vencido
    fecha_vencimiento = db.Column(db.Date, nullable=True)  # Cuándo se debe pagar
    fecha_pago_real = db.Column(db.DateTime, nullable=True)  # Cuándo se pagó realmente
    
    # Relaciones
    usuario = db.relationship('Usuario', foreign_keys=[usuario_id], backref='gastos_registrados')
    aprobado_por = db.relationship('Usuario', foreign_keys=[aprobado_por_id], backref='gastos_aprobados')


# =========================
# Consumo Interno (solo para administración)
# =========================
class ConsumoInterno(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey('item_menu.id'), nullable=False)
    cantidad = db.Column(db.Integer, default=1)
    costo = db.Column(db.Float, default=0.0)  # Costo para el dueño por unidad
    fecha = db.Column(db.DateTime, default=datetime.now)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    notas = db.Column(db.Text)

    item = db.relationship('ItemMenu', backref='consumos_internos', lazy='joined')
    usuario = db.relationship('Usuario', backref='consumos_registrados')

# =========================
# MODELOS DE DOMICILIOS
# =========================

class EstadoDomicilio:
    """Estados posibles de un domicilio"""
    PENDIENTE = 'pendiente'
    PREPARANDO = 'preparando'
    LISTO = 'listo'
    EN_CAMINO = 'en_camino'
    ENTREGADO = 'entregado'
    CANCELADO = 'cancelado'

class Domicilio(db.Model):
    """
    RAZÓN: Gestionar pedidos a domicilio con toda su información.
    Similar a una sesión de mesa, pero para entregas externas.
    """
    # =================================================================
    # IDENTIFICADOR ÚNICO
    # =================================================================
    id = db.Column(db.Integer, primary_key=True)
    
    # =================================================================
    # INFORMACIÓN DEL CLIENTE (datos de contacto y dirección)
    # =================================================================
    cliente_nombre = db.Column(db.String(200), nullable=False)       # "Juan Pérez"
    cliente_telefono = db.Column(db.String(50), nullable=False)      # "3001234567"
    cliente_direccion = db.Column(db.Text, nullable=False)           # "Calle 10 #5-20"
    cliente_barrio = db.Column(db.String(100))                       # "Centro"
    cliente_referencias = db.Column(db.Text)                         # "Casa azul, portón negro"
    
    # =================================================================
    # INFORMACIÓN DEL PEDIDO (fechas y tiempos)
    # =================================================================
    fecha_pedido = db.Column(db.DateTime, default=datetime.now, nullable=False)
    fecha_entrega_estimada = db.Column(db.DateTime)                  # Opcional
    fecha_entrega_real = db.Column(db.DateTime)                      # Cuando se entrega
    
    # =================================================================
    # ESTADO DEL DOMICILIO (flujo del pedido)
    # =================================================================
    # Valores posibles: 'pendiente', 'preparando', 'listo', 'en_camino', 'entregado', 'cancelado'
    estado = db.Column(db.String(20), default=EstadoDomicilio.PENDIENTE)
    
    # =================================================================
    # COSTOS (cálculo del total)
    # =================================================================
    subtotal = db.Column(db.Float, default=0)              # Suma de productos
    costo_domicilio = db.Column(db.Float, default=0)       # Costo de envío
    propina = db.Column(db.Float, default=0)               # Propina opcional
    total = db.Column(db.Float, default=0)                 # subtotal + costo_domicilio + propina
    
    # =================================================================
    # MÉTODO DE PAGO (cómo paga el cliente)
    # =================================================================
    metodo_pago = db.Column(db.String(50), default='efectivo')  # 'efectivo', 'tarjeta', 'transferencia'
    pagado = db.Column(db.Boolean, default=False)               # Si ya pagó
    
    # =================================================================
    # RESPONSABLES (quién toma y quién entrega)
    # =================================================================
    # ID del usuario que tomó el pedido (mesero/admin)
    tomado_por_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    
    # ID del repartidor asignado (puede ser NULL si aún no se asigna)
    repartidor_id = db.Column(db.Integer, db.ForeignKey('usuario.id'))
    
    # =================================================================
    # FACTURACIÓN (relación con tabla Factura)
    # =================================================================
    # ID de la factura generada (NULL si aún no se factura)
    factura_id = db.Column(db.Integer, db.ForeignKey('factura.id'))
    
    # =================================================================
    # NOTAS ADICIONALES
    # =================================================================
    notas = db.Column(db.Text)                          # Notas del pedido
    notas_cancelacion = db.Column(db.Text)              # Por qué se canceló
    
    # =================================================================
    # TIMESTAMPS (control de tiempos)
    # =================================================================
    estado_actualizado = db.Column(db.DateTime, default=datetime.now)
    
    # =================================================================
    # RELACIONES (conexiones con otras tablas)
    # =================================================================
    
    # Relación con Usuario (quién tomó el pedido)
    tomado_por = db.relationship('Usuario', 
                                 foreign_keys=[tomado_por_id], 
                                 backref='domicilios_tomados')
    
    # Relación con Usuario (quién entrega)
    repartidor = db.relationship('Usuario', 
                                 foreign_keys=[repartidor_id], 
                                 backref='domicilios_asignados')
    
    # Relación con ItemDomicilio (productos del pedido)
    # lazy='select' = carga bajo demanda
    # cascade='all, delete-orphan' = si eliminas el domicilio, elimina los items
    items = db.relationship('ItemDomicilio', 
                           backref='domicilio', 
                           lazy='select', 
                           cascade='all, delete-orphan')
    
    # =================================================================
    # 🔥 RELACIÓN CON FACTURA (LA MÁS IMPORTANTE PARA TU PROBLEMA)
    # =================================================================
    # Esta línea crea una relación bidireccional:
    # - domicilio.factura → accede a la factura
    # - factura.domicilios → accede a los domicilios de esa factura
    #
    # lazy='dynamic' significa que factura.domicilios devuelve una query
    # que puedes filtrar o usar .first(), .all(), etc.
    factura = db.relationship('Factura', 
                             backref=db.backref('domicilios', lazy='dynamic'))
    
    # =================================================================
    # PROPIEDADES CALCULADAS (@property)
    # =================================================================
    
    @property
    def tiempo_transcurrido(self):
        """
        Calcula cuánto tiempo ha pasado desde que se tomó el pedido
        Retorna string legible: "15 min" o "1h 30min"
        """
        delta = datetime.now() - self.fecha_pedido
        minutos = int(delta.total_seconds() / 60)
        if minutos < 60:
            return f"{minutos} min"
        else:
            horas = minutos // 60
            mins = minutos % 60
            return f"{horas}h {mins}min"
    
    @property
    def esta_retrasado(self):
        """
        Verifica si el domicilio está tardando más de lo normal
        Retorna True si lleva más de 45 minutos y no ha sido entregado
        """
        if self.estado in [EstadoDomicilio.ENTREGADO, EstadoDomicilio.CANCELADO]:
            return False
        
        delta = datetime.now() - self.fecha_pedido
        minutos = int(delta.total_seconds() / 60)
        
        # Alertar si lleva más de 45 minutos y no ha sido entregado
        return minutos > 45
    
    @property
    def color_estado(self):
        """
        Color del badge según el estado (para mostrar en HTML)
        Retorna código de color hexadecimal
        """
        colores = {
            'pendiente': '#ffc107',      # amarillo/warning
            'preparando': '#17a2b8',     # cyan/info
            'listo': '#007bff',          # azul/primary
            'en_camino': '#6f42c1',      # púrpura
            'entregado': '#28a745',      # verde/success
            'cancelado': '#dc3545'       # rojo/danger
        }
        return colores.get(self.estado, '#6c757d')
    
    @property
    def domiciliario(self):
        """
        Nombre del repartidor asignado
        Retorna "No asignado" si no hay repartidor
        """
        if self.repartidor:
            return self.repartidor.nombre
        return "No asignado"


class ItemDomicilio(db.Model):
    """
    RAZÓN: Items individuales de cada domicilio.
    Similar a los pedidos de mesa, pero asociados a domicilios.
    """
    id = db.Column(db.Integer, primary_key=True)
    domicilio_id = db.Column(db.Integer, db.ForeignKey('domicilio.id'), nullable=False)
    
    # Producto
    item_menu_id = db.Column(db.Integer, db.ForeignKey('item_menu.id'))
    producto_nombre = db.Column(db.String(200), nullable=False)
    cantidad = db.Column(db.Integer, default=1)
    precio_unitario = db.Column(db.Float, nullable=False)
    
    # Personalización
    notas = db.Column(db.Text)
    
    # NUEVO: Estado de preparación en cocina
    estado_cocina = db.Column(db.String(20), default='pendiente')  # pendiente, preparando, listo
    
    # Relaciones
    item_menu = db.relationship('ItemMenu', backref='items_domicilio')
    
    @property
    def subtotal(self):
        return self.cantidad * self.precio_unitario
    
    @property
    def producto(self):
        """Alias para compatibilidad con templates"""
        return self.producto_nombre


class Repartidor(db.Model):
    """
    RAZÓN: Gestionar información de repartidores.
    Opcional: Si los repartidores no son usuarios del sistema.
    """
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(200), nullable=False)
    telefono = db.Column(db.String(50))
    placa_vehiculo = db.Column(db.String(20))
    tipo_vehiculo = db.Column(db.String(50))  # moto, bicicleta, carro
    activo = db.Column(db.Boolean, default=True)
    fecha_registro = db.Column(db.DateTime, default=datetime.now)
    
    # Estadísticas
    total_domicilios = db.Column(db.Integer, default=0)
    calificacion_promedio = db.Column(db.Float, default=5.0)
    
    # Relaciones (si no usas Usuario como repartidor)
    # domicilios = db.relationship('Domicilio', backref='repartidor_externo')


class ZonaDelivery(db.Model):
    """
    RAZÓN: Definir zonas de cobertura y costos de envío.
    Permite calcular automáticamente el costo según el barrio.
    """
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)  # "Centro", "Norte", "Sur"
    barrios = db.Column(db.Text)  # Lista de barrios separados por comas
    costo_envio = db.Column(db.Float, default=0)
    tiempo_estimado = db.Column(db.Integer, default=30)  # minutos
    activa = db.Column(db.Boolean, default=True)
    orden = db.Column(db.Integer, default=0)
    
    @property
    def lista_barrios(self):
        """Devuelve lista de barrios"""
        if self.barrios:
            return [b.strip() for b in self.barrios.split(',')]
        return []

# =========================
# RUTAS
# =========================
# ==========================================
# ACTUALIZAR RUTA DE FACTURAR SESIÓN
# ==========================================

# REEMPLAZA tu ruta actual de facturar_sesion con esta versión mejorada:

@app.route("/facturar_sesion/<int:sesion_id>", methods=["GET", "POST"])
@login_required
def facturar_sesion(sesion_id):
    """
    Generar factura para una sesión - AHORA CON ESTADO DE PAGO
    """
    sesion = Sesion.query.get_or_404(sesion_id)
    config = ConfiguracionRestaurante.query.first()
    
    if not config:
        config = ConfiguracionRestaurante()
        db.session.add(config)
        db.session.commit()
    
    if request.method == "POST":
        # Obtener datos del formulario
        metodo_pago = request.form.get("metodo_pago", "efectivo")
        propina = request.form.get("propina", 0, type=float)
        cliente_nombre = request.form.get("cliente_nombre", "")
        cliente_documento = request.form.get("cliente_documento", "")
        notas = request.form.get("notas", "")
        
        # NUEVOS CAMPOS
        estado_pago = request.form.get("estado_pago", "pagada")
        fecha_vencimiento_str = request.form.get("fecha_vencimiento")
        
        # Desglose de pago para método mixto
        desglose_pago = None
        if metodo_pago == "mixto":
            desglose_pago = {
                "efectivo": request.form.get("efectivo", 0, type=float),
                "tarjeta": request.form.get("tarjeta", 0, type=float),
                "transferencia": request.form.get("transferencia", 0, type=float)
            }
        
        # Calcular totales (usar agregación en DB para eficiencia)
        subtotal = db.session.query(db.func.coalesce(db.func.sum(Pedido.cantidad * Pedido.precio_unitario), 0)).filter(Pedido.sesion_id == sesion.id).scalar() or 0
        iva = 0  # Sin IVA
        total = subtotal + propina

        # Generar número consecutivo
        ultima_factura = Factura.query.order_by(Factura.id.desc()).first()
        if ultima_factura:
            ultimo_num = int(ultima_factura.numero_consecutivo.split('-')[1])
            nuevo_num = ultimo_num + 1
        else:
            nuevo_num = 1
        
        numero_consecutivo = f"FACT-{nuevo_num:06d}"
        
        # Convertir fecha de vencimiento
        fecha_vencimiento = None
        if fecha_vencimiento_str and estado_pago == 'pendiente':
            fecha_vencimiento = datetime.strptime(fecha_vencimiento_str, '%Y-%m-%d').date()
        
        # Fecha de pago real
        fecha_pago_real = datetime.now() if estado_pago == 'pagada' else None
        
        # Saldo pendiente
        saldo_pendiente = total if estado_pago == 'pendiente' else 0
        
        # Crear factura
        factura = Factura(
            numero_consecutivo=numero_consecutivo,
            sesion_id=sesion_id,
            subtotal=subtotal,
            iva=iva,
            propina=propina,
            total=total,
            metodo_pago=metodo_pago,
            desglose_pago=json.dumps(desglose_pago) if desglose_pago else None,
            cliente_nombre=cliente_nombre,
            cliente_documento=cliente_documento,
            notas=notas,
            estado_pago=estado_pago,
            fecha_vencimiento=fecha_vencimiento,
            fecha_pago_real=fecha_pago_real,
            saldo_pendiente=saldo_pendiente
        )
        
        # Actualizar sesión
        sesion.total = total
        sesion.activa = False
        sesion.fecha_fin = datetime.now()
        
        # Marcar todos los pedidos como pagados (actualización en bloque)
        db.session.query(Pedido).filter(Pedido.sesion_id == sesion.id).update({"pagado": True, "estado": "entregado"}, synchronize_session=False)
        
        db.session.add(factura)
        db.session.commit()
        
        flash(f'Factura {numero_consecutivo} generada exitosamente', 'success')
        return redirect(url_for('ver_factura', factura_id=factura.id))
    
    # GET: Calcular totales para mostrar en el formulario (usar agregación en DB)
    subtotal = db.session.query(db.func.coalesce(db.func.sum(Pedido.cantidad * Pedido.precio_unitario), 0)).filter(Pedido.sesion_id == sesion.id).scalar() or 0
    iva = 0  # Sin IVA
    
    # ============================================
    # SOLUCIÓN: PASAR datetime AL TEMPLATE
    # ============================================
    return render_template("facturar_sesion.html", 
                         sesion=sesion, 
                         config=config,
                         subtotal=subtotal,
                         iva=iva,
                         datetime=datetime)  # ← ESTA LÍNEA ES CLAVE

# =================================================================
# REEMPLAZAR LA RUTA ver_factura EN app.py (línea ~620)
# =================================================================

@app.route("/factura/<int:factura_id>")
@login_required
def ver_factura(factura_id):
    """Ver una factura generada - OPTIMIZADA PARA IMPRESORAS TÉRMICAS"""
    factura = Factura.query.get_or_404(factura_id)
    config = ConfiguracionRestaurante.query.first()
    
    # Crear configuración por defecto si no existe
    if not config:
        config = ConfiguracionRestaurante()
        db.session.add(config)
        db.session.commit()
    
    # Parsear desglose de pago si existe
    desglose = None
    if factura.desglose_pago:
        try:
            desglose = json.loads(factura.desglose_pago)
        except:
            desglose = None
    
    return render_template("ver_factura.html", 
                         factura=factura, 
                         config=config,
                         desglose=desglose)

@app.route("/facturas")
@login_required
def lista_facturas():
    """Listar todas las facturas"""
    fecha_param = request.args.get('fecha')
    
    if fecha_param:
        try:
            fecha_obj = datetime.strptime(fecha_param, '%Y-%m-%d').date()
            facturas = Factura.query.filter(
                db.func.date(Factura.fecha_emision) == fecha_obj
            ).order_by(Factura.fecha_emision.desc()).all()
        except ValueError:
            flash('Fecha inválida', 'error')
            facturas = Factura.query.order_by(Factura.fecha_emision.desc()).limit(50).all()
    else:
        # Últimas 50 facturas
        facturas = Factura.query.order_by(Factura.fecha_emision.desc()).limit(50).all()
    
    return render_template("lista_facturas.html", facturas=facturas)

# ==========================================
# RUTAS PARA CONSUMO INTERNO (ADMIN)
# ==========================================
@app.route('/consumo_interno')
@login_required
def lista_consumos_internos():
    if getattr(current_user, 'rol', None) != 'admin':
        flash('No tienes permisos para ver consumos internos', 'error')
        return redirect(url_for('dashboard'))

    fecha = request.args.get('fecha')
    fecha_inicio = request.args.get('fecha_inicio')
    fecha_fin = request.args.get('fecha_fin')

    query = ConsumoInterno.query

    # Si se especifica `fecha`, interpretamos el día como [fecha 03:00, fecha+1 03:00)
    if fecha:
        try:
            d = datetime.strptime(fecha, '%Y-%m-%d').date()
            start = datetime(d.year, d.month, d.day, 3, 0, 0)
            end = start + timedelta(days=1)
            query = query.filter(ConsumoInterno.fecha >= start, ConsumoInterno.fecha < end)
        except ValueError:
            flash('Fecha inválida', 'error')
    else:
        # Si se usa rango, aplicamos cierre diario a las 03:00: fecha_inicio comienza a las 03:00; fecha_fin termina el día siguiente a las 03:00 (exclusivo)
        if fecha_inicio:
            try:
                fi_date = datetime.strptime(fecha_inicio, '%Y-%m-%d').date()
                start = datetime(fi_date.year, fi_date.month, fi_date.day, 3, 0, 0)
                query = query.filter(ConsumoInterno.fecha >= start)
            except ValueError:
                flash('Fecha inicio inválida', 'error')
        if fecha_fin:
            try:
                ff_date = datetime.strptime(fecha_fin, '%Y-%m-%d').date()
                end = datetime(ff_date.year, ff_date.month, ff_date.day, 3, 0, 0) + timedelta(days=1)
                query = query.filter(ConsumoInterno.fecha < end)
            except ValueError:
                flash('Fecha fin inválida', 'error')

    try:
        consumos = query.order_by(ConsumoInterno.fecha.desc()).limit(200).all()
        total_costo = sum(c.costo * c.cantidad for c in consumos)
    except OperationalError:
        # Tabla aún no creada; instrucciones para el desarrollador
        flash("La tabla 'consumo_interno' no existe. Ejecuta `python update_database.py` para crearla.", 'error')
        return redirect(url_for('dashboard'))

    return render_template('consumo_interno/lista_consumos.html', consumos=consumos, total_costo=total_costo)


@app.route('/consumo_interno/nuevo', methods=['GET', 'POST'])
@login_required
def nuevo_consumo_interno():
    if getattr(current_user, 'rol', None) != 'admin':
        flash('No tienes permisos para crear consumos internos', 'error')
        return redirect(url_for('dashboard'))

    items = ItemMenu.query.order_by(ItemMenu.nombre).all()
    users = Usuario.query.order_by(Usuario.nombre).all()

    if request.method == 'POST':
        item_id = request.form.get('item_id', type=int)
        usuario_id = request.form.get('usuario_id', type=int)
        cantidad = request.form.get('cantidad', 1, type=int)
        costo = request.form.get('costo', 0.0, type=float)
        notas = request.form.get('notas')

        if not item_id or not usuario_id or cantidad <= 0:
            flash('Item, usuario o cantidad inválida', 'error')
            return redirect(url_for('nuevo_consumo_interno'))

        # Verificar que el usuario seleccionado exista
        usuario = Usuario.query.get(usuario_id)
        if not usuario:
            flash('Usuario seleccionado no existe', 'error')
            return redirect(url_for('nuevo_consumo_interno'))

        consumo = ConsumoInterno(item_id=item_id, cantidad=cantidad, costo=costo, usuario_id=usuario_id, notas=notas)
        db.session.add(consumo)
        db.session.commit()
        flash('Consumo interno registrado', 'success')
        return redirect(url_for('lista_consumos_internos'))

    return render_template('consumo_interno/nuevo_consumo.html', items=items, users=users) 


@app.route('/consumo_interno/<int:consumo_id>/eliminar', methods=['POST'])
@login_required
def eliminar_consumo_interno(consumo_id):
    if getattr(current_user, 'rol', None) != 'admin':
        flash('No tienes permisos para eliminar consumos internos', 'error')
        return redirect(url_for('dashboard'))

    consumo = ConsumoInterno.query.get_or_404(consumo_id)
    try:
        db.session.delete(consumo)
        db.session.commit()
        flash('Consumo interno eliminado', 'success')
    except Exception:
        db.session.rollback()
        flash('Error al eliminar consumo interno', 'error')

    return redirect(url_for('lista_consumos_internos'))


@app.route('/factura/<int:factura_id>/editar', methods=['GET', 'POST'])
@login_required
def editar_factura(factura_id):
    factura = Factura.query.get_or_404(factura_id)
    if getattr(current_user, 'rol', None) != 'admin':
        flash('No tienes permisos para editar facturas', 'error')
        return redirect(url_for('ver_factura', factura_id=factura_id))

    config = ConfiguracionRestaurante.query.first()

    if request.method == 'POST':
        metodo_pago = request.form.get('metodo_pago', factura.metodo_pago)
        propina = request.form.get('propina', factura.propina, type=float)
        cliente_nombre = request.form.get('cliente_nombre', factura.cliente_nombre)
        cliente_documento = request.form.get('cliente_documento', factura.cliente_documento)
        notas = request.form.get('notas', factura.notas)
        estado_pago = request.form.get('estado_pago', factura.estado_pago)
        fecha_vencimiento_str = request.form.get('fecha_vencimiento')

        desglose_pago = None
        if metodo_pago == 'mixto':
            desglose_pago = {
                'efectivo': request.form.get('efectivo', 0, type=float),
                'tarjeta': request.form.get('tarjeta', 0, type=float),
                'transferencia': request.form.get('transferencia', 0, type=float)
            }

        # Recalcular subtotal desde la sesión asociada
        subtotal = db.session.query(db.func.coalesce(db.func.sum(Pedido.cantidad * Pedido.precio_unitario), 0)).filter(Pedido.sesion_id == factura.sesion_id).scalar() or 0
        iva = factura.iva if factura.iva is not None else 0
        total = subtotal + propina + (iva or 0)

        # Actualizar campos
        factura.metodo_pago = metodo_pago
        factura.propina = propina
        factura.cliente_nombre = cliente_nombre
        factura.cliente_documento = cliente_documento
        factura.notas = notas
        factura.estado_pago = estado_pago
        factura.desglose_pago = json.dumps(desglose_pago) if desglose_pago else None
        factura.subtotal = subtotal
        factura.total = total

        # Fecha vencimiento
        if fecha_vencimiento_str:
            try:
                factura.fecha_vencimiento = datetime.strptime(fecha_vencimiento_str, '%Y-%m-%d').date()
            except Exception:
                factura.fecha_vencimiento = None
        else:
            factura.fecha_vencimiento = None

        # Ajustes según estado de pago
        if estado_pago == 'pagada':
            factura.fecha_pago_real = datetime.now()
            factura.saldo_pendiente = 0
        elif estado_pago == 'pendiente':
            factura.fecha_pago_real = None
            factura.saldo_pendiente = total
        db.session.commit()
        flash(f'Factura {factura.numero_consecutivo} actualizada', 'success')
        return redirect(url_for('ver_factura', factura_id=factura.id))

    # GET
    desglose = json.loads(factura.desglose_pago) if factura.desglose_pago else None
    return render_template('editar_factura.html', factura=factura, config=config, desglose=desglose)


@app.route('/factura/<int:factura_id>/eliminar', methods=['POST'])
@login_required
def eliminar_factura(factura_id):
    """
    RAZÓN: Eliminar facturas y revertir los cambios asociados.
    Funciona tanto para facturas de sesiones como de domicilios.
    Al eliminar, la factura desaparece de los reportes de ingresos automáticamente.
    """
    factura = Factura.query.get_or_404(factura_id)
    
    # Solo admin puede eliminar facturas
    if getattr(current_user, 'rol', None) != 'admin':
        flash('No tienes permisos para eliminar facturas', 'error')
        return redirect(url_for('ver_factura', factura_id=factura_id))

    numero_factura = factura.numero_consecutivo
    monto = factura.total
    
    try:
        # ============================================
        # CASO 1: FACTURA DE SESIÓN (MESA)
        # ============================================
        if factura.sesion_id:
            sesion = factura.sesion
            if sesion:
                # Reactivar la sesión
                sesion.activa = True
                sesion.fecha_fin = None
                sesion.total = 0
                
                # Revertir estado de los pedidos
                db.session.query(Pedido).filter(
                    Pedido.sesion_id == sesion.id
                ).update({
                    "pagado": False,
                    "estado": "pendiente"
                }, synchronize_session=False)
        
        # ============================================
        # CASO 2: FACTURA DE DOMICILIO
        # ============================================
        else:
            # Buscar domicilio asociado a esta factura
            domicilio = Domicilio.query.filter_by(factura_id=factura_id).first()
            if domicilio:
                # Desasociar la factura del domicilio
                domicilio.factura_id = None
                domicilio.pagado = False
                # El domicilio queda en su estado actual (entregado)
                # pero sin factura asociada, permitiendo re-facturar
        
        # ============================================
        # ELIMINAR LA FACTURA
        # ============================================
        db.session.delete(factura)
        db.session.commit()
        
        flash(f'✓ Factura {numero_factura} eliminada exitosamente (${monto:,.0f})', 'success')
        flash('La factura ha sido eliminada de los reportes de ingresos', 'info')
        
    except Exception as e:
        db.session.rollback()
        flash(f'❌ Error al eliminar la factura: {str(e)}', 'error')
        return redirect(url_for('ver_factura', factura_id=factura_id))
    
    # Redirigir a la lista de facturas
    return redirect(url_for('lista_facturas'))

# ==========================================
# RUTAS PARA CUENTAS POR COBRAR
# ==========================================

@app.route("/cuentas_por_cobrar")
@login_required
def cuentas_por_cobrar():
    """
    RAZÓN: Vista principal de deudas de clientes.
    Muestra facturas pendientes de cobro y vencidas.
    """
    # Obtener filtros
    estado = request.args.get('estado', 'todos')  # todos, pendiente, vencida, pagada
    
    # Query base
    query = Factura.query
    
    # Aplicar filtros
    if estado != 'todos':
        query = query.filter(Factura.estado_pago == estado)
    
    # Ordenar por fecha de vencimiento
    facturas = query.order_by(Factura.fecha_vencimiento).all()
    
    # Actualizar estados de facturas vencidas automáticamente
    from datetime import date
    hoy = date.today()
    
    for factura in facturas:
        if factura.estado_pago == 'pendiente' and factura.fecha_vencimiento and factura.fecha_vencimiento < hoy:
            factura.estado_pago = 'vencida'
    
    db.session.commit()
    
    # Calcular totales
    total_pendiente = sum(f.saldo_pendiente or f.total for f in facturas if f.estado_pago == 'pendiente')
    total_vencido = sum(f.saldo_pendiente or f.total for f in facturas if f.estado_pago == 'vencida')
    total_general = total_pendiente + total_vencido
    
    # Agrupar por cliente
    facturas_por_cliente = {}
    for factura in facturas:
        if factura.estado_pago in ['pendiente', 'vencida'] and factura.cliente_nombre:
            cliente = factura.cliente_nombre
            if cliente not in facturas_por_cliente:
                facturas_por_cliente[cliente] = {
                    'cliente': cliente,
                    'total': 0,
                    'cantidad': 0
                }
            facturas_por_cliente[cliente]['total'] += (factura.saldo_pendiente or factura.total)
            facturas_por_cliente[cliente]['cantidad'] += 1
    
    # ============================================
    # SOLUCIÓN: AGREGAR datetime AL RETURN
    # ============================================
    return render_template("cuentas/cuentas_por_cobrar.html",
                         facturas=facturas,
                         total_pendiente=total_pendiente,
                         total_vencido=total_vencido,
                         total_general=total_general,
                         facturas_por_cliente=facturas_por_cliente.values(),
                         estado_filtro=estado,
                         datetime=datetime)  # ← AGREGAR ESTA LÍNEA
                         

@app.route("/marcar_factura_pagada/<int:factura_id>", methods=["POST"])
@login_required
def marcar_factura_pagada(factura_id):
    """
    RAZÓN: Marca una factura como pagada cuando el cliente paga.
    """
    factura = Factura.query.get_or_404(factura_id)
    
    monto_pago = request.form.get('monto_pago', type=float)
    
    if not monto_pago:
        monto_pago = factura.saldo_pendiente or factura.total
    
    # Calcular saldo pendiente
    saldo_actual = factura.saldo_pendiente or factura.total
    nuevo_saldo = saldo_actual - monto_pago
    
    if nuevo_saldo <= 0:
        # Pago completo
        factura.estado_pago = 'pagada'
        factura.saldo_pendiente = 0
        factura.fecha_pago_real = datetime.now()
        flash(f'Factura {factura.numero_consecutivo} marcada como pagada completamente', 'success')
    else:
        # Pago parcial
        factura.saldo_pendiente = nuevo_saldo
        flash(f'Pago parcial registrado. Saldo pendiente: ${nuevo_saldo:,.2f}', 'success')
    
    db.session.commit()
    
    return redirect(request.referrer or url_for('cuentas_por_cobrar'))




@app.route("/configuracion_restaurante", methods=["GET", "POST"])
@login_required
def configuracion_restaurante():
    """Configurar datos del restaurante"""
    if current_user.rol != 'admin':
        flash('Solo los administradores pueden modificar la configuración', 'error')
        return redirect(url_for('dashboard'))
    
    config = ConfiguracionRestaurante.query.first()
    
    if not config:
        config = ConfiguracionRestaurante()
        db.session.add(config)
        db.session.commit()
    
    if request.method == "POST":
        config.nombre = request.form.get("nombre")
        config.nit = request.form.get("nit")
        config.direccion = request.form.get("direccion")
        config.ciudad = request.form.get("ciudad")
        config.telefono = request.form.get("telefono")
        config.email = request.form.get("email", "")
        config.regimen = request.form.get("regimen")
        config.resolucion_dian = request.form.get("resolucion_dian", "")
        config.rango_facturacion = request.form.get("rango_facturacion", "")
        config.iva_porcentaje = request.form.get("iva_porcentaje", 19.0, type=float)
        config.logo_url = request.form.get("logo_url", "")
        
        db.session.commit()
        flash('Configuración actualizada exitosamente', 'success')
        return redirect(url_for('configuracion_restaurante'))
    
    return render_template("configuracion_restaurante.html", config=config, now=datetime.now())

# Actualizar la función init_db() para incluir la configuración inicial
def init_db_facturacion():
    """Agregar esto dentro de tu función init_db() existente"""
    # Crear configuración del restaurante si no existe
    if ConfiguracionRestaurante.query.count() == 0:
        config = ConfiguracionRestaurante(
            nombre='Mi Restaurante',
            nit='900.000.000-0',
            direccion='Calle 123 #45-67',
            ciudad='Zarzal, Valle del Cauca',
            telefono='(+57) 300 000 0000',
            regimen='Régimen Simplificado'
        )
        db.session.add(config)
        db.session.commit()

        
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
    
    # Obtener solo sesiones activas de hoy
    hoy = datetime.now().date()
    sesiones_activas = Sesion.query.filter(
        Sesion.activa == True,
        db.func.date(Sesion.fecha_inicio) == hoy
    ).all()
    
    # Agrupar por mesa con información de la sesión activa
    info_mesas = {}
    for mesa in mesas:
        # Buscar sesión activa de esta mesa
        sesion_activa = next((s for s in sesiones_activas if s.mesa_id == mesa.id), None)
        
        if sesion_activa:
            # Obtener pedidos de la sesión activa
            pedidos = Pedido.query.filter_by(sesion_id=sesion_activa.id).all()
            
            info_mesas[mesa.id] = {
                'mesa': mesa,
                'sesion': sesion_activa,
                'pedidos': pedidos,
                'tiene_pendientes': any(not p.pagado for p in pedidos),
                'todos_entregados': all(p.estado == 'entregado' for p in pedidos),
                'total_pedidos': len(pedidos),
                'hora_inicio': sesion_activa.fecha_inicio.strftime('%H:%M')
            }
        else:
            info_mesas[mesa.id] = {
                'mesa': mesa,
                'sesion': None,
                'pedidos': [],
                'tiene_pendientes': False,
                'todos_entregados': False,
                'total_pedidos': 0,
                'hora_inicio': None
            }
    
    return render_template("dashboard.html", 
                         mesas=mesas, 
                         info_mesas=info_mesas,
                         now=datetime.now())

@app.route("/nuevo_pedido/<int:mesa_id>", methods=["GET", "POST"])
@login_required
def nuevo_pedido(mesa_id):
    mesa = Mesa.query.get_or_404(mesa_id)
    
    if request.method == "POST":
        producto = request.form.get("producto")
        cantidad = request.form.get("cantidad", 1, type=int)
        precio_unitario = request.form.get("precio_unitario", 0, type=float)
        notas = request.form.get("notas", "")
        
        # Buscar o crear sesión activa para esta mesa
        sesion_activa = Sesion.query.filter_by(
            mesa_id=mesa_id,
            activa=True
        ).first()
        
        if not sesion_activa:
            # Crear nueva sesión
            sesion_activa = Sesion(mesa_id=mesa_id)
            db.session.add(sesion_activa)
            db.session.flush()  # Para obtener el ID
        
        pedido = Pedido(
            mesa_id=mesa_id,
            sesion_id=sesion_activa.id,
            mesero_id=current_user.id,
            producto=producto,
            cantidad=cantidad,
            precio_unitario=precio_unitario,
            notas=notas
        )
        
        db.session.add(pedido)
        db.session.commit()
        
        total = precio_unitario * cantidad
        flash(f'Pedido agregado: {cantidad}x {producto} = ${total:.2f}', 'success')
        return redirect(url_for('ver_mesa', mesa_id=mesa_id))
    
    # Obtener todos los items del menú disponibles, agrupados por categoría
    items_menu = ItemMenu.query.filter_by(disponible=True).order_by(
        ItemMenu.categoria_id, ItemMenu.orden
    ).all()
    
    return render_template("nuevo_pedido.html", mesa=mesa, items_menu=items_menu)

@app.route("/mesa/<int:mesa_id>")
@login_required
def ver_mesa(mesa_id):
    mesa = Mesa.query.get_or_404(mesa_id)
    
    # Obtener sesión activa
    sesion_activa = Sesion.query.filter_by(
        mesa_id=mesa_id,
        activa=True
    ).first()
    
    # Obtener pedidos de la sesión activa y calcular totales
    pedidos_actuales = []
    totales_sesion_activa = {
        'total_general': 0,
        'total_pagado': 0,
        'total_pendiente': 0
    }
    
    if sesion_activa:
        pedidos_actuales = Pedido.query.filter_by(
            sesion_id=sesion_activa.id
        ).order_by(Pedido.fecha.desc()).all()
        
        # Calcular totales
        for pedido in pedidos_actuales:
            subtotal = pedido.cantidad * pedido.precio_unitario
            totales_sesion_activa['total_general'] += subtotal
            
            if pedido.pagado:
                totales_sesion_activa['total_pagado'] += subtotal
            else:
                totales_sesion_activa['total_pendiente'] += subtotal
    
    # Obtener sesiones anteriores de hoy con sus totales calculados
    hoy = datetime.now().date()
    sesiones_anteriores = Sesion.query.filter(
        Sesion.mesa_id == mesa_id,
        Sesion.activa == False,
        db.func.date(Sesion.fecha_inicio) == hoy
    ).order_by(Sesion.fecha_inicio.desc()).all()
    
    # Calcular totales para cada sesión anterior
    sesiones_con_totales = []
    for sesion in sesiones_anteriores:
        total_sesion = 0
        total_pagado_sesion = 0
        total_pendiente_sesion = 0
        
        for pedido in sesion.pedidos:
            subtotal = pedido.cantidad * pedido.precio_unitario
            total_sesion += subtotal
            
            if pedido.pagado:
                total_pagado_sesion += subtotal
            else:
                total_pendiente_sesion += subtotal
        
        sesiones_con_totales.append({
            'sesion': sesion,
            'total_general': total_sesion,
            'total_pagado': total_pagado_sesion,
            'total_pendiente': total_pendiente_sesion
        })
    
    return render_template("ver_mesa.html", 
                         mesa=mesa, 
                         pedidos=pedidos_actuales,
                         sesion_activa=sesion_activa,
                         totales_sesion_activa=totales_sesion_activa,
                         sesiones_anteriores=sesiones_con_totales,
                         current_user=current_user)

@app.route("/cocina")
@login_required
def cocina():
    hoy = datetime.now().date()
    
    pedidos_pendientes = Pedido.query.filter(
        db.func.date(Pedido.fecha) == hoy,
        Pedido.estado.in_(['pendiente', 'preparando'])
    ).order_by(Pedido.fecha).all()
    
    return render_template(
        "cocina.html",
        pedidos=pedidos_pendientes,
        now=datetime.now()
    )

@app.route("/api/cocina/pedidos")
@login_required
def api_cocina_pedidos():
    hoy = datetime.now().date()
    
    pedidos = Pedido.query.filter(
        db.func.date(Pedido.fecha) == hoy,
        Pedido.estado.in_(['pendiente', 'preparando'])
    ).order_by(Pedido.fecha).all()
    
    data = []
    for p in pedidos:
        data.append({
            "id": p.id,
            "mesa": p.mesa.numero,
            "producto": p.producto,
            "cantidad": p.cantidad,
            "notas": p.notas or "",
            "estado": p.estado,
            "fecha": p.fecha.isoformat()
        })
    
    return jsonify(data)


@app.route("/actualizar_estado/<int:pedido_id>/<estado>")
@login_required
def actualizar_estado(pedido_id, estado):
    pedido = Pedido.query.get_or_404(pedido_id)
    estados_validos = ['pendiente', 'preparando', 'listo', 'entregado']
    
    if estado in estados_validos:
        pedido.estado = estado
        try:
            pedido.estado_actualizado = datetime.now()
        except Exception:
            # En caso de que la columna no exista en DB todavía
            pass
        db.session.commit()
        flash(f'Estado actualizado a: {estado}', 'success')
        # Si se marcó como 'listo' y quien lo marcó NO es mesero, creamos una notificación para meseros
        if estado == 'listo' and getattr(current_user, 'rol', None) != 'mesero':
            # No necesitamos guardar una entidad de notificación; el JS de meseros hará polling por pedidos 'listo' recientes
            pass
    
    return redirect(request.referrer or url_for('dashboard'))

@app.route("/marcar_pagado/<int:pedido_id>")
@login_required
def marcar_pagado(pedido_id):
    pedido = Pedido.query.get_or_404(pedido_id)
    pedido.pagado = True
    db.session.commit()
    flash('Pedido marcado como pagado', 'success')
    return redirect(request.referrer or url_for('dashboard'))


@app.route('/notificaciones/pendientes')
@login_required
def notificaciones_pendientes():
    """Endpoint que devuelve pedidos marcados como 'listo' desde un timestamp 'since'.
    Parámetros: since (ISO 8601 string). Solo accesible a usuarios con rol 'mesero'."""
    if getattr(current_user, 'rol', None) != 'mesero':
        return jsonify([])

    since = request.args.get('since')
    try:
        since_dt = datetime.fromisoformat(since) if since else (datetime.now() - timedelta(seconds=10))
    except Exception:
        since_dt = datetime.now() - timedelta(seconds=10)

    pedidos = Pedido.query.filter(
        Pedido.estado == 'listo',
        Pedido.estado_actualizado > since_dt
    ).order_by(Pedido.estado_actualizado.asc()).all()

    data = []
    for p in pedidos:
        data.append({
            'id': p.id,
            'mesa': p.mesa.numero if p.mesa else None,
            'producto': p.producto,
            'cantidad': p.cantidad,
            'estado_actualizado': p.estado_actualizado.isoformat() if p.estado_actualizado else None
        })

    return jsonify(data)

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
    sesiones_por_dia = {}
    totales_por_dia = {}
    
    if fecha_param:
        try:
            fecha_seleccionada = datetime.strptime(fecha_param, '%Y-%m-%d').date()
            # Obtener sesiones de la fecha seleccionada
            sesiones = Sesion.query.filter(
                db.func.date(Sesion.fecha_inicio) == fecha_seleccionada
            ).order_by(Sesion.fecha_inicio.desc()).all()
            
            if sesiones:
                fecha_str = fecha_seleccionada.strftime('%Y-%m-%d')
                sesiones_por_dia[fecha_str] = sesiones
                
                # Calcular totales para esa fecha
                total_general = sum(s.total or 0 for s in sesiones if not s.activa)
                total_facturado = sum(s.total or 0 for s in sesiones if not s.activa and s.facturas)
                total_sin_facturar = sum(s.total or 0 for s in sesiones if not s.activa and not s.facturas)
                sesiones_activas = sum(1 for s in sesiones if s.activa)
                sesiones_cerradas = sum(1 for s in sesiones if not s.activa)
                
                totales_por_dia[fecha_str] = {
                    'total_general': total_general,
                    'total_facturado': total_facturado,
                    'total_sin_facturar': total_sin_facturar,
                    'sesiones_activas': sesiones_activas,
                    'sesiones_cerradas': sesiones_cerradas
                }
        except ValueError:
            flash('Fecha inválida', 'error')
            fecha_seleccionada = None
    
    # Si no hay fecha seleccionada, mostrar últimos 7 días
    if not fecha_param:
        sesiones = Sesion.query.order_by(Sesion.fecha_inicio.desc()).limit(100).all()
        
        for sesion in sesiones:
            fecha_str = sesion.fecha_inicio.strftime('%Y-%m-%d')
            if fecha_str not in sesiones_por_dia:
                sesiones_por_dia[fecha_str] = []
            sesiones_por_dia[fecha_str].append(sesion)
        
        # Limitar a los últimos 7 días
        sesiones_por_dia = dict(list(sesiones_por_dia.items())[:7])
        
        # Calcular totales para cada día
        for fecha_str, sesiones_dia in sesiones_por_dia.items():
            total_general = sum(s.total or 0 for s in sesiones_dia if not s.activa)
            total_facturado = sum(s.total or 0 for s in sesiones_dia if not s.activa and s.facturas)
            total_sin_facturar = sum(s.total or 0 for s in sesiones_dia if not s.activa and not s.facturas)
            sesiones_activas = sum(1 for s in sesiones_dia if s.activa)
            sesiones_cerradas = sum(1 for s in sesiones_dia if not s.activa)
            
            totales_por_dia[fecha_str] = {
                'total_general': total_general,
                'total_facturado': total_facturado,
                'total_sin_facturar': total_sin_facturar,
                'sesiones_activas': sesiones_activas,
                'sesiones_cerradas': sesiones_cerradas
            }
    
    return render_template("historial.html", 
                         sesiones_por_dia=sesiones_por_dia,
                         totales_por_dia=totales_por_dia,
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


@app.route("/api/cocina/verificar_nuevos")
@login_required
def verificar_nuevos_pedidos():
    """
    RAZÓN: Endpoint ligero para verificar nuevos pedidos sin recargar toda la página
    """
    hoy = datetime.now().date()
    
    # Solo pedidos pendientes y preparando
    pedidos = Pedido.query.filter(
        db.func.date(Pedido.fecha) == hoy,
        Pedido.estado.in_(['pendiente', 'preparando'])
    ).all()
    
    # Devolver solo los IDs y timestamps
    data = {
        'pedidos': [
            {
                'id': p.id,
                'mesa': p.mesa.numero,
                'producto': p.producto,
                'cantidad': p.cantidad,
                'estado': p.estado,
                'timestamp': p.fecha.timestamp()
            }
            for p in pedidos
        ],
        'total': len(pedidos),
        'pendientes': len([p for p in pedidos if p.estado == 'pendiente']),
        'preparando': len([p for p in pedidos if p.estado == 'preparando'])
    }
    
    return jsonify(data)

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
    """Cierra la sesión activa de una mesa"""
    sesion_activa = Sesion.query.filter_by(
        mesa_id=mesa_id,
        activa=True
    ).first()
    
    if sesion_activa:
        # Marcar todos los pedidos como entregados y pagados
        for pedido in sesion_activa.pedidos:
            pedido.pagado = True
            pedido.estado = 'entregado'
        
        # Cerrar sesión
        sesion_activa.activa = False
        sesion_activa.fecha_fin = datetime.now()
        
        db.session.commit()
        flash(f'Mesa {mesa_id} liberada exitosamente', 'success')
    else:
        flash('No hay sesión activa para esta mesa', 'error')
    
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
# RUTAS DEL MENÚ PÚBLICO
# =========================

@app.route("/menu")
def menu_publico():
    """Menú público accesible sin login"""
    categorias = CategoriaMenu.query.filter_by(activa=True).order_by(CategoriaMenu.orden).all()
    return render_template("menu_publico.html", categorias=categorias)

@app.route("/administrar_menu")
@login_required
def administrar_menu():
    """Panel de administración del menú"""
    if current_user.rol != 'admin':
        flash('Solo los administradores pueden gestionar el menú', 'error')
        return redirect(url_for('dashboard'))
    
    categorias = CategoriaMenu.query.order_by(CategoriaMenu.orden).all()
    items = ItemMenu.query.order_by(ItemMenu.categoria_id, ItemMenu.orden).all()
    
    return render_template("administrar_menu.html", categorias=categorias, items=items)

@app.route("/agregar_categoria", methods=["POST"])
@login_required
def agregar_categoria():
    if current_user.rol != 'admin':
        flash('Solo los administradores pueden agregar categorías', 'error')
        return redirect(url_for('dashboard'))
    
    nombre = request.form.get("nombre")
    orden = request.form.get("orden", 0, type=int)
    
    categoria = CategoriaMenu(nombre=nombre, orden=orden)
    db.session.add(categoria)
    db.session.commit()
    
    flash(f'Categoría "{nombre}" agregada exitosamente', 'success')
    return redirect(url_for('administrar_menu'))

@app.route("/agregar_item", methods=["POST"])
@login_required
def agregar_item():
    if current_user.rol != 'admin':
        flash('Solo los administradores pueden agregar items', 'error')
        return redirect(url_for('dashboard'))
    
    nombre = request.form.get("nombre")
    descripcion = request.form.get("descripcion", "")
    precio = request.form.get("precio", type=float)
    categoria_id = request.form.get("categoria_id", type=int)
    imagen_url = request.form.get("imagen_url", "")
    orden = request.form.get("orden", 0, type=int)
    
    item = ItemMenu(
        nombre=nombre,
        descripcion=descripcion,
        precio=precio,
        categoria_id=categoria_id,
        imagen_url=imagen_url,
        orden=orden
    )
    
    db.session.add(item)
    db.session.commit()
    
    flash(f'Platillo "{nombre}" agregado exitosamente', 'success')
    return redirect(url_for('administrar_menu'))

@app.route("/editar_item/<int:item_id>", methods=["POST"])
@login_required
def editar_item(item_id):
    if current_user.rol != 'admin':
        flash('Solo los administradores pueden editar items', 'error')
        return redirect(url_for('dashboard'))
    
    item = ItemMenu.query.get_or_404(item_id)
    
    item.nombre = request.form.get("nombre")
    item.descripcion = request.form.get("descripcion", "")
    item.precio = request.form.get("precio", type=float)
    item.categoria_id = request.form.get("categoria_id", type=int)
    item.imagen_url = request.form.get("imagen_url", "")
    item.orden = request.form.get("orden", 0, type=int)
    
    db.session.commit()
    
    flash(f'Platillo "{item.nombre}" actualizado', 'success')
    return redirect(url_for('administrar_menu'))

@app.route("/toggle_item/<int:item_id>")
@login_required
def toggle_item(item_id):
    if current_user.rol != 'admin':
        flash('Solo los administradores pueden modificar items', 'error')
        return redirect(url_for('dashboard'))
    
    item = ItemMenu.query.get_or_404(item_id)
    item.disponible = not item.disponible
    db.session.commit()
    
    estado = "disponible" if item.disponible else "no disponible"
    flash(f'"{item.nombre}" marcado como {estado}', 'success')
    return redirect(url_for('administrar_menu'))

@app.route("/eliminar_item/<int:item_id>", methods=["POST"])
@login_required
def eliminar_item(item_id):
    if current_user.rol != 'admin':
        flash('Solo los administradores pueden eliminar items', 'error')
        return redirect(url_for('dashboard'))
    
    item = ItemMenu.query.get_or_404(item_id)
    nombre = item.nombre
    db.session.delete(item)
    db.session.commit()
    
    flash(f'"{nombre}" eliminado del menú', 'success')
    return redirect(url_for('administrar_menu'))

@app.route("/eliminar_categoria/<int:categoria_id>", methods=["POST"])
@login_required
def eliminar_categoria(categoria_id):
    if current_user.rol != 'admin':
        flash('Solo los administradores pueden eliminar categorías', 'error')
        return redirect(url_for('dashboard'))
    
    categoria = CategoriaMenu.query.get_or_404(categoria_id)
    
    if categoria.items:
        flash(f'No se puede eliminar "{categoria.nombre}" porque tiene platillos asociados', 'error')
    else:
        nombre = categoria.nombre
        db.session.delete(categoria)
        db.session.commit()
        flash(f'Categoría "{nombre}" eliminada', 'success')
    
    return redirect(url_for('administrar_menu'))

# ==========================================
# RUTAS PARA GESTIÓN DE GASTOS
# ==========================================

@app.route("/gastos")
@login_required
def lista_gastos():
    """
    RAZÓN: Vista principal de gastos con filtros por fecha y categoría.
    Permite búsqueda rápida y visualización de totales.
    """
    # Obtener parámetros de filtro
    fecha_inicio = request.args.get('fecha_inicio')
    fecha_fin = request.args.get('fecha_fin')
    categoria_id = request.args.get('categoria_id', type=int)
    
    # Query base
    query = Gasto.query
    
    # Aplicar filtros
    if fecha_inicio:
        try:
            # Empezamos el día a las 03:00 (cierre a partir de las 03:00)
            fecha_inicio_obj = datetime.strptime(fecha_inicio, '%Y-%m-%d').replace(hour=3, minute=0, second=0)
            query = query.filter(Gasto.fecha >= fecha_inicio_obj)
        except ValueError:
            flash('Fecha de inicio inválida', 'error')
    
    if fecha_fin:
        try:
            # La fecha de fin será el inicio del día siguiente a las 03:00 (end-exclusive)
            fecha_fin_obj = datetime.strptime(fecha_fin, '%Y-%m-%d').replace(hour=3, minute=0, second=0) + timedelta(days=1)
            query = query.filter(Gasto.fecha < fecha_fin_obj)
        except ValueError:
            flash('Fecha de fin inválida', 'error')
    
    if categoria_id:
        query = query.filter(Gasto.categoria_id == categoria_id)
    
    # Obtener gastos ordenados por fecha descendente
    gastos = query.order_by(Gasto.fecha.desc()).all()
    
    # Calcular totales
    total_gastos = sum(g.monto for g in gastos)
    
    # Totales por categoría (para el dashboard)
    totales_por_categoria = db.session.query(
        CategoriaGasto.nombre,
        CategoriaGasto.color,
        db.func.sum(Gasto.monto).label('total')
    ).join(Gasto).group_by(CategoriaGasto.id).all()
    
    # Obtener todas las categorías para el filtro
    categorias = CategoriaGasto.query.filter_by(activa=True).order_by(CategoriaGasto.nombre).all()
    
    return render_template("gastos/lista_gastos.html",
                         gastos=gastos,
                         total_gastos=total_gastos,
                         totales_por_categoria=totales_por_categoria,
                         categorias=categorias,
                         fecha_inicio=fecha_inicio,
                         fecha_fin=fecha_fin,
                         categoria_id=categoria_id)


# ==========================================
# ACTUALIZAR RUTA DE NUEVO GASTO
# ==========================================

# REEMPLAZA tu ruta actual de nuevo_gasto con esta versión mejorada:

@app.route("/gasto/nuevo", methods=["GET", "POST"])
@login_required
def nuevo_gasto():
    """
    RAZÓN: Formulario para registrar un nuevo gasto.
    Ahora incluye estado de pago y fecha de vencimiento.
    """
    if current_user.rol == 'cocina':
        flash('No tienes permisos para registrar gastos', 'error')
        return redirect(url_for('dashboard'))
    
    if request.method == "POST":
        try:
            # Obtener datos del formulario
            fecha_str = request.form.get("fecha")
            concepto = request.form.get("concepto")
            monto = request.form.get("monto", type=float)
            categoria_id = request.form.get("categoria_id", type=int)
            proveedor_id = request.form.get("proveedor_id", type=int) or None
            metodo_pago = request.form.get("metodo_pago", "efectivo")
            numero_factura = request.form.get("numero_factura", "")
            notas = request.form.get("notas", "")
            
            # NUEVOS CAMPOS
            estado_pago = request.form.get("estado_pago", "pagado")
            fecha_vencimiento_str = request.form.get("fecha_vencimiento")
            
            # Validaciones básicas
            if not concepto or monto <= 0:
                flash('Debes completar todos los campos requeridos', 'error')
                return redirect(url_for('nuevo_gasto'))
            
            # Convertir fecha
            if fecha_str:
                fecha = datetime.strptime(fecha_str, '%Y-%m-%dT%H:%M')
            else:
                fecha = datetime.now()
            
            # Convertir fecha de vencimiento
            fecha_vencimiento = None
            if fecha_vencimiento_str and estado_pago == 'pendiente':
                fecha_vencimiento = datetime.strptime(fecha_vencimiento_str, '%Y-%m-%d').date()
            
            # Si está pagado, la fecha de pago es ahora
            fecha_pago_real = datetime.now() if estado_pago == 'pagado' else None
            
            # Crear gasto
            gasto = Gasto(
                fecha=fecha,
                concepto=concepto,
                monto=monto,
                categoria_id=categoria_id,
                proveedor_id=proveedor_id,
                usuario_id=current_user.id,
                metodo_pago=metodo_pago,
                numero_factura=numero_factura,
                notas=notas,
                estado_pago=estado_pago,
                fecha_vencimiento=fecha_vencimiento,
                fecha_pago_real=fecha_pago_real
            )
            
            db.session.add(gasto)
            db.session.commit()
            
            # Verificar si se excedió el presupuesto
            verificar_presupuesto(categoria_id)
            
            flash(f'Gasto de ${monto:,.2f} registrado exitosamente', 'success')
            return redirect(url_for('lista_gastos'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error al registrar el gasto: {str(e)}', 'error')
            return redirect(url_for('nuevo_gasto'))
    
    # GET: Mostrar formulario
    categorias = CategoriaGasto.query.filter_by(activa=True).order_by(CategoriaGasto.nombre).all()
    proveedores = Proveedor.query.filter_by(activo=True).order_by(Proveedor.nombre).all()
    
    return render_template("gastos/nuevo_gasto.html",
                         categorias=categorias,
                         proveedores=proveedores,
                         now=datetime.now())


# Función auxiliar para verificar presupuestos
def verificar_presupuesto(categoria_id):
    """
    RAZÓN: Verifica si se excedió el presupuesto de una categoría
    y genera alertas en flash messages.
    """
    from datetime import datetime
    mes_actual = datetime.now().month
    anio_actual = datetime.now().year
    
    presupuesto = Presupuesto.query.filter_by(
        categoria_id=categoria_id,
        mes=mes_actual,
        anio=anio_actual,
        activo=True
    ).first()
    
    if presupuesto:
        porcentaje = presupuesto.porcentaje_usado
        categoria = presupuesto.categoria.nombre
        
        if porcentaje >= 100:
            flash(f'⚠️ ALERTA: Presupuesto de "{categoria}" EXCEDIDO ({porcentaje:.1f}%)', 'error')
        elif porcentaje >= presupuesto.alerta_porcentaje:
            flash(f'⚠️ Advertencia: Presupuesto de "{categoria}" al {porcentaje:.1f}%', 'error')



@app.route("/gasto/editar/<int:gasto_id>", methods=["GET", "POST"])
@login_required
def editar_gasto(gasto_id):
    """
    RAZÓN: Permite corregir errores en gastos registrados.
    Solo admin puede editar gastos de otros usuarios.
    """
    gasto = Gasto.query.get_or_404(gasto_id)
    
    # Verificar permisos
    if current_user.rol != 'admin' and gasto.usuario_id != current_user.id:
        flash('No tienes permisos para editar este gasto', 'error')
        return redirect(url_for('lista_gastos'))
    
    if request.method == "POST":
        try:
            fecha_str = request.form.get("fecha")
            gasto.concepto = request.form.get("concepto")
            gasto.monto = request.form.get("monto", type=float)
            gasto.categoria_id = request.form.get("categoria_id", type=int)
            gasto.proveedor_id = request.form.get("proveedor_id", type=int) or None
            gasto.metodo_pago = request.form.get("metodo_pago")
            gasto.numero_factura = request.form.get("numero_factura", "")
            gasto.notas = request.form.get("notas", "")
            
            if fecha_str:
                gasto.fecha = datetime.strptime(fecha_str, '%Y-%m-%dT%H:%M')
            
            db.session.commit()
            flash('Gasto actualizado exitosamente', 'success')
            return redirect(url_for('lista_gastos'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error al actualizar: {str(e)}', 'error')
    
    categorias = CategoriaGasto.query.filter_by(activa=True).order_by(CategoriaGasto.nombre).all()
    proveedores = Proveedor.query.filter_by(activo=True).order_by(Proveedor.nombre).all()
    
    return render_template("gastos/editar_gasto.html",
                         gasto=gasto,
                         categorias=categorias,
                         proveedores=proveedores)


@app.route("/gasto/eliminar/<int:gasto_id>", methods=["POST"])
@login_required
def eliminar_gasto(gasto_id):
    """
    RAZÓN: Solo admin puede eliminar gastos para mantener integridad.
    Se elimina permanentemente (no soft delete).
    """
    if current_user.rol != 'admin':
        flash('Solo administradores pueden eliminar gastos', 'error')
        return redirect(url_for('lista_gastos'))
    
    gasto = Gasto.query.get_or_404(gasto_id)
    monto = gasto.monto
    concepto = gasto.concepto
    
    db.session.delete(gasto)
    db.session.commit()
    
    flash(f'Gasto eliminado: {concepto} (${monto:,.2f})', 'success')
    return redirect(url_for('lista_gastos'))

# ==========================================
# RUTAS PARA CUENTAS POR PAGAR
# ==========================================

@app.route("/cuentas_por_pagar")
@login_required
def cuentas_por_pagar():
    """
    RAZÓN: Vista principal de deudas con proveedores.
    Muestra gastos pendientes de pago y vencidos.
    """
    # Obtener filtros
    estado = request.args.get('estado', 'todos')
    proveedor_id = request.args.get('proveedor_id', type=int)
    
    # Query base
    query = Gasto.query
    
    # Aplicar filtros
    if estado != 'todos':
        query = query.filter(Gasto.estado_pago == estado)
    
    if proveedor_id:
        query = query.filter(Gasto.proveedor_id == proveedor_id)
    
    # Ordenar por fecha de vencimiento
    gastos = query.order_by(Gasto.fecha_vencimiento).all()
    
    # Actualizar estados de gastos vencidos automáticamente
    from datetime import date
    hoy = date.today()
    
    for gasto in gastos:
        if gasto.estado_pago == 'pendiente' and gasto.fecha_vencimiento and gasto.fecha_vencimiento < hoy:
            gasto.estado_pago = 'vencido'
    
    db.session.commit()
    
    # Calcular totales
    total_pendiente = sum(g.monto for g in gastos if g.estado_pago == 'pendiente')
    total_vencido = sum(g.monto for g in gastos if g.estado_pago == 'vencido')
    total_general = total_pendiente + total_vencido
    
    # Agrupar por proveedor
    gastos_por_proveedor = {}
    for gasto in gastos:
        if gasto.estado_pago in ['pendiente', 'vencido']:
            if gasto.proveedor:
                prov_id = gasto.proveedor.id
                if prov_id not in gastos_por_proveedor:
                    gastos_por_proveedor[prov_id] = {
                        'proveedor': gasto.proveedor,
                        'total': 0,
                        'cantidad': 0
                    }
                gastos_por_proveedor[prov_id]['total'] += gasto.monto
                gastos_por_proveedor[prov_id]['cantidad'] += 1
    
    # Obtener proveedores para filtro
    proveedores = Proveedor.query.filter_by(activo=True).order_by(Proveedor.nombre).all()
    
    # ============================================
    # SOLUCIÓN: AGREGAR datetime AL RETURN
    # ============================================
    return render_template("cuentas/cuentas_por_pagar.html",
                         gastos=gastos,
                         total_pendiente=total_pendiente,
                         total_vencido=total_vencido,
                         total_general=total_general,
                         gastos_por_proveedor=gastos_por_proveedor.values(),
                         proveedores=proveedores,
                         estado_filtro=estado,
                         proveedor_filtro=proveedor_id,
                         datetime=datetime)  # ← AGREGAR ESTA LÍNEA


@app.route("/marcar_gasto_pagado/<int:gasto_id>", methods=["POST"])
@login_required
def marcar_gasto_pagado(gasto_id):
    """
    RAZÓN: Marca un gasto como pagado cuando realmente se paga.
    """
    if current_user.rol not in ['admin', 'mesero']:
        flash('No tienes permisos para esta acción', 'error')
        return redirect(url_for('cuentas_por_pagar'))
    
    gasto = Gasto.query.get_or_404(gasto_id)
    
    gasto.estado_pago = 'pagado'
    gasto.fecha_pago_real = datetime.now()
    
    db.session.commit()
    
    flash(f'Gasto marcado como pagado: {gasto.concepto}', 'success')
    return redirect(request.referrer or url_for('cuentas_por_pagar'))


@app.route("/gasto/editar_vencimiento/<int:gasto_id>", methods=["POST"])
@login_required
def editar_vencimiento_gasto(gasto_id):
    """
    RAZÓN: Permite cambiar la fecha de vencimiento de un gasto pendiente.
    """
    if current_user.rol != 'admin':
        flash('Solo administradores pueden modificar vencimientos', 'error')
        return redirect(url_for('cuentas_por_pagar'))
    
    gasto = Gasto.query.get_or_404(gasto_id)
    
    nueva_fecha = request.form.get('fecha_vencimiento')
    if nueva_fecha:
        gasto.fecha_vencimiento = datetime.strptime(nueva_fecha, '%Y-%m-%d').date()
        db.session.commit()
        flash('Fecha de vencimiento actualizada', 'success')
    
    return redirect(url_for('cuentas_por_pagar'))




# ==========================================
# RUTAS PARA PROVEEDORES
# ==========================================

@app.route("/proveedores")
@login_required
def lista_proveedores():
    """RAZÓN: Gestionar base de datos de proveedores"""
    proveedores = Proveedor.query.order_by(Proveedor.nombre).all()
    return render_template("gastos/lista_proveedores.html", proveedores=proveedores)


@app.route("/proveedor/nuevo", methods=["GET", "POST"])
@login_required
def nuevo_proveedor():
    """RAZÓN: Agregar nuevos proveedores al sistema"""
    if request.method == "POST":
        proveedor = Proveedor(
            nombre=request.form.get("nombre"),
            nit=request.form.get("nit", ""),
            telefono=request.form.get("telefono", ""),
            email=request.form.get("email", ""),
            direccion=request.form.get("direccion", ""),
            notas=request.form.get("notas", "")
        )
        
        db.session.add(proveedor)
        db.session.commit()
        
        flash(f'Proveedor {proveedor.nombre} agregado', 'success')
        return redirect(url_for('lista_proveedores'))
    
    return render_template("gastos/nuevo_proveedor.html")


@app.route("/proveedor/editar/<int:proveedor_id>", methods=["GET", "POST"])
@login_required
def editar_proveedor(proveedor_id):
    """RAZÓN: Actualizar información de proveedores"""
    proveedor = Proveedor.query.get_or_404(proveedor_id)
    
    if request.method == "POST":
        proveedor.nombre = request.form.get("nombre")
        proveedor.nit = request.form.get("nit", "")
        proveedor.telefono = request.form.get("telefono", "")
        proveedor.email = request.form.get("email", "")
        proveedor.direccion = request.form.get("direccion", "")
        proveedor.notas = request.form.get("notas", "")
        
        db.session.commit()
        flash('Proveedor actualizado', 'success')
        return redirect(url_for('lista_proveedores'))
    
    return render_template("gastos/editar_proveedor.html", proveedor=proveedor)


@app.route("/proveedor/toggle/<int:proveedor_id>")
@login_required
def toggle_proveedor(proveedor_id):
    """RAZÓN: Activar/desactivar proveedores sin eliminarlos"""
    if current_user.rol != 'admin':
        flash('Solo administradores pueden modificar proveedores', 'error')
        return redirect(url_for('lista_proveedores'))
    
    proveedor = Proveedor.query.get_or_404(proveedor_id)
    proveedor.activo = not proveedor.activo
    db.session.commit()
    
    estado = "activado" if proveedor.activo else "desactivado"
    flash(f'Proveedor {proveedor.nombre} {estado}', 'success')
    return redirect(url_for('lista_proveedores'))


# ==========================================
# REPORTES FINANCIEROS
# ==========================================

@app.route("/reportes/financiero")
@login_required
def reporte_financiero():
    """
    RAZÓN: Vista consolidada de ingresos vs gastos.
    El reporte más importante para tomar decisiones.
    """
    # Obtener rango de fechas (por defecto, mes actual)
    fecha_inicio = request.args.get('fecha_inicio')
    fecha_fin = request.args.get('fecha_fin')
    
    if not fecha_inicio:
        # Primer día del mes actual
        hoy = datetime.now()
        fecha_inicio = hoy.replace(day=1).strftime('%Y-%m-%d')
    
    if not fecha_fin:
        # Hoy
        fecha_fin = datetime.now().strftime('%Y-%m-%d')
    
    # Convertir a objetos datetime
    # IMPORTANTE: Definimos el inicio del día a las 03:00 (cierre a partir de las 03:00)
    fecha_inicio_obj = datetime.strptime(fecha_inicio, '%Y-%m-%d').replace(hour=3, minute=0, second=0)
    # Fecha fin es el inicio del día siguiente a las 03:00 (end-exclusive)
    fecha_fin_obj = datetime.strptime(fecha_fin, '%Y-%m-%d').replace(hour=3, minute=0, second=0) + timedelta(days=1)

    # INGRESOS: Sumar facturas del período (end-exclusive: >= inicio, < fin)
    ingresos = db.session.query(
        db.func.sum(Factura.total)
    ).filter(
        Factura.fecha_emision >= fecha_inicio_obj,
        Factura.fecha_emision < fecha_fin_obj
    ).scalar() or 0
    
    # GASTOS: Sumar gastos del período (end-exclusive)
    gastos_total = db.session.query(
        db.func.sum(Gasto.monto)
    ).filter(
        Gasto.fecha >= fecha_inicio_obj,
        Gasto.fecha < fecha_fin_obj
    ).scalar() or 0
    
    # UTILIDAD = INGRESOS - GASTOS
    utilidad = ingresos - gastos_total
    margen = (utilidad / ingresos * 100) if ingresos > 0 else 0
    
    # Gastos por categoría - CONVERTIR A LISTA DE TUPLAS
    gastos_por_categoria_raw = db.session.query(
        CategoriaGasto.nombre,
        CategoriaGasto.color,
        db.func.sum(Gasto.monto).label('total'),
        db.func.count(Gasto.id).label('cantidad')
    ).join(Gasto).filter(
        Gasto.fecha >= fecha_inicio_obj,
        Gasto.fecha < fecha_fin_obj
    ).group_by(CategoriaGasto.id).order_by(db.desc('total')).all()
    
    # SOLUCIÓN: Convertir Row objects a lista de listas para JSON
    gastos_por_categoria = []
    gastos_por_categoria_tabla = []
    
    for row in gastos_por_categoria_raw:
        # Para el gráfico (formato JSON)
        gastos_por_categoria.append([
            row[0],  # nombre
            row[1],  # color
            float(row[2])  # total
        ])
        
        # Para la tabla HTML (objeto completo)
        gastos_por_categoria_tabla.append({
            'nombre': row[0],
            'color': row[1],
            'total': float(row[2]),
            'cantidad': row[3]
        })
    
    # Evolución diaria de ingresos y gastos (para gráfico)
    # Cada "día" va desde 03:00 del día hasta 03:00 del día siguiente
    dias_rango = (fecha_fin_obj - fecha_inicio_obj).days
    evolucion_diaria = []
    
    for i in range(dias_rango):
        dia_inicio = fecha_inicio_obj + timedelta(days=i)
        dia_fin = dia_inicio + timedelta(days=1)
        
        ingresos_dia = db.session.query(
            db.func.sum(Factura.total)
        ).filter(
            Factura.fecha_emision >= dia_inicio,
            Factura.fecha_emision < dia_fin
        ).scalar() or 0
        
        gastos_dia = db.session.query(
            db.func.sum(Gasto.monto)
        ).filter(
            Gasto.fecha >= dia_inicio,
            Gasto.fecha < dia_fin
        ).scalar() or 0
        
        evolucion_diaria.append({
            'fecha': dia_inicio.strftime('%Y-%m-%d'),
            'ingresos': float(ingresos_dia),
            'gastos': float(gastos_dia),
            'utilidad': float(ingresos_dia - gastos_dia)
        })
    
    return render_template("reportes/financiero.html",
                         fecha_inicio=fecha_inicio,
                         fecha_fin=fecha_fin,
                         ingresos=float(ingresos),
                         gastos_total=float(gastos_total),
                         utilidad=float(utilidad),
                         margen=float(margen),
                         gastos_por_categoria=gastos_por_categoria,  # Para JSON/gráficos
                         gastos_por_categoria_tabla=gastos_por_categoria_tabla,  # Para tabla HTML
                         evolucion_diaria=evolucion_diaria,
                         now=datetime.now())
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

        if CategoriaGasto.query.count() == 0:
            categorias_default = [
                {'nombre': 'Ingredientes y Materia Prima', 'descripcion': 'Compras de alimentos, bebidas y suministros de cocina', 'color': '#28a745'},
                {'nombre': 'Salarios y Nómina', 'descripcion': 'Pagos a empleados, prestaciones y seguridad social', 'color': '#007bff'},
                {'nombre': 'Servicios Públicos', 'descripcion': 'Agua, luz, gas, internet, teléfono', 'color': '#ffc107'},
                {'nombre': 'Arriendo', 'descripcion': 'Pago de arriendo del local', 'color': '#dc3545'},
                {'nombre': 'Mantenimiento', 'descripcion': 'Reparaciones, limpieza, mantenimiento de equipos', 'color': '#6c757d'},
                {'nombre': 'Marketing', 'descripcion': 'Publicidad, redes sociales, volantes', 'color': '#e83e8c'},
                {'nombre': 'Impuestos', 'descripcion': 'Impuestos, declaraciones, trámites legales', 'color': '#fd7e14'},
                {'nombre': 'Otros Gastos', 'descripcion': 'Gastos misceláneos', 'color': '#6610f2'}
            ]
            
            for cat_data in categorias_default:
                categoria = CategoriaGasto(**cat_data)
                db.session.add(categoria)
        
        db.session.commit()
        print("Categorías de gastos inicializadas correctamente")

# ==========================================
# RUTAS PARA PRESUPUESTOS
# ==========================================

@app.route("/presupuestos")
@login_required
def lista_presupuestos():
    """
    RAZÓN: Vista principal de presupuestos por categoría.
    Muestra límites de gasto y alertas.
    """
    if current_user.rol != 'admin':
        flash('Solo administradores pueden ver presupuestos', 'error')
        return redirect(url_for('dashboard'))
    
    # Obtener mes y año actual
    from datetime import datetime
    mes_actual = datetime.now().month
    anio_actual = datetime.now().year
    
    # Obtener presupuestos del mes actual
    presupuestos = Presupuesto.query.filter_by(
        mes=mes_actual,
        anio=anio_actual,
        activo=True
    ).all()
    
    # Si no hay presupuestos para este mes, obtener todos los activos
    if not presupuestos:
        presupuestos = Presupuesto.query.filter_by(activo=True).all()
    
    # Calcular totales
    total_presupuestado = sum(p.monto_limite for p in presupuestos)
    total_gastado = sum(p.gasto_actual for p in presupuestos)
    total_disponible = total_presupuestado - total_gastado
    
    # Contar alertas
    alertas = sum(1 for p in presupuestos if p.estado in ['alerta', 'excedido'])
    excedidos = sum(1 for p in presupuestos if p.estado == 'excedido')
    
    return render_template("presupuestos/lista_presupuestos.html",
                         presupuestos=presupuestos,
                         total_presupuestado=total_presupuestado,
                         total_gastado=total_gastado,
                         total_disponible=total_disponible,
                         alertas=alertas,
                         excedidos=excedidos,
                         mes_actual=mes_actual,
                         anio_actual=anio_actual)


@app.route("/presupuesto/nuevo", methods=["GET", "POST"])
@login_required
def nuevo_presupuesto():
    """
    RAZÓN: Crear un nuevo presupuesto para una categoría.
    """
    if current_user.rol != 'admin':
        flash('Solo administradores pueden crear presupuestos', 'error')
        return redirect(url_for('dashboard'))
    
    if request.method == "POST":
        categoria_id = request.form.get("categoria_id", type=int)
        monto_limite = request.form.get("monto_limite", type=float)
        periodo = request.form.get("periodo", "mensual")
        mes = request.form.get("mes", type=int)
        anio = request.form.get("anio", type=int)
        alerta_porcentaje = request.form.get("alerta_porcentaje", 80, type=int)
        
        # Verificar si ya existe un presupuesto para esta categoría/mes/año
        existe = Presupuesto.query.filter_by(
            categoria_id=categoria_id,
            mes=mes,
            anio=anio,
            activo=True
        ).first()
        
        if existe:
            flash('Ya existe un presupuesto activo para esta categoría en ese período', 'error')
            return redirect(url_for('nuevo_presupuesto'))
        
        presupuesto = Presupuesto(
            categoria_id=categoria_id,
            monto_limite=monto_limite,
            periodo=periodo,
            mes=mes,
            anio=anio,
            alerta_porcentaje=alerta_porcentaje
        )
        
        db.session.add(presupuesto)
        db.session.commit()
        
        flash('Presupuesto creado exitosamente', 'success')
        return redirect(url_for('lista_presupuestos'))
    
    # GET
    categorias = CategoriaGasto.query.filter_by(activa=True).order_by(CategoriaGasto.nombre).all()
    
    from datetime import datetime
    mes_actual = datetime.now().month
    anio_actual = datetime.now().year
    
    return render_template("presupuestos/nuevo_presupuesto.html",
                         categorias=categorias,
                         mes_actual=mes_actual,
                         anio_actual=anio_actual)


@app.route("/presupuesto/editar/<int:presupuesto_id>", methods=["GET", "POST"])
@login_required
def editar_presupuesto(presupuesto_id):
    """
    RAZÓN: Modificar un presupuesto existente.
    """
    if current_user.rol != 'admin':
        flash('Solo administradores pueden editar presupuestos', 'error')
        return redirect(url_for('dashboard'))
    
    presupuesto = Presupuesto.query.get_or_404(presupuesto_id)
    
    if request.method == "POST":
        presupuesto.monto_limite = request.form.get("monto_limite", type=float)
        presupuesto.alerta_porcentaje = request.form.get("alerta_porcentaje", type=int)
        
        db.session.commit()
        flash('Presupuesto actualizado', 'success')
        return redirect(url_for('lista_presupuestos'))
    
    return render_template("presupuestos/editar_presupuesto.html",
                         presupuesto=presupuesto)


@app.route("/presupuesto/desactivar/<int:presupuesto_id>")
@login_required
def desactivar_presupuesto(presupuesto_id):
    """
    RAZÓN: Desactivar un presupuesto sin eliminarlo.
    """
    if current_user.rol != 'admin':
        flash('Solo administradores pueden desactivar presupuestos', 'error')
        return redirect(url_for('dashboard'))
    
    presupuesto = Presupuesto.query.get_or_404(presupuesto_id)
    presupuesto.activo = False
    
    db.session.commit()
    flash('Presupuesto desactivado', 'success')
    return redirect(url_for('lista_presupuestos'))


@app.route("/presupuesto/copiar_mes_siguiente", methods=["POST"])
@login_required
def copiar_presupuestos_mes_siguiente():
    """
    RAZÓN: Copia todos los presupuestos del mes actual al mes siguiente.
    Útil para no tener que recrearlos cada mes.
    """
    if current_user.rol != 'admin':
        flash('Solo administradores pueden copiar presupuestos', 'error')
        return redirect(url_for('dashboard'))
    
    from datetime import datetime
    from dateutil.relativedelta import relativedelta
    
    mes_actual = datetime.now().month
    anio_actual = datetime.now().year
    
    # Calcular mes siguiente
    fecha_siguiente = datetime.now() + relativedelta(months=1)
    mes_siguiente = fecha_siguiente.month
    anio_siguiente = fecha_siguiente.year
    
    # Obtener presupuestos del mes actual
    presupuestos_actuales = Presupuesto.query.filter_by(
        mes=mes_actual,
        anio=anio_actual,
        activo=True
    ).all()
    
    if not presupuestos_actuales:
        flash('No hay presupuestos activos en el mes actual para copiar', 'error')
        return redirect(url_for('lista_presupuestos'))
    
    # Verificar si ya existen presupuestos para el mes siguiente
    existe = Presupuesto.query.filter_by(
        mes=mes_siguiente,
        anio=anio_siguiente,
        activo=True
    ).first()
    
    if existe:
        flash(f'Ya existen presupuestos para {mes_siguiente}/{anio_siguiente}', 'error')
        return redirect(url_for('lista_presupuestos'))
    
    # Copiar presupuestos
    copiados = 0
    for p in presupuestos_actuales:
        nuevo = Presupuesto(
            categoria_id=p.categoria_id,
            monto_limite=p.monto_limite,
            periodo=p.periodo,
            mes=mes_siguiente,
            anio=anio_siguiente,
            alerta_porcentaje=p.alerta_porcentaje
        )
        db.session.add(nuevo)
        copiados += 1
    
    db.session.commit()
    flash(f'{copiados} presupuesto(s) copiados a {mes_siguiente}/{anio_siguiente}', 'success')
    return redirect(url_for('lista_presupuestos'))

# =========================
# RUTAS DE DOMICILIOS
# =========================

@app.route("/domicilios")
@login_required
def lista_domicilios():
    """
    RAZÓN: Vista principal de domicilios con filtros por estado y fecha.
    """
    # Obtener filtros
    estado = request.args.get('estado', 'todos')
    fecha = request.args.get('fecha')
    
    # Query base
    query = Domicilio.query
    
    # Filtrar por estado
    if estado != 'todos':
        query = query.filter(Domicilio.estado == estado)
    
    # Filtrar por fecha (con lógica de cierre a las 03:00)
    if fecha:
        try:
            fecha_obj = datetime.strptime(fecha, '%Y-%m-%d').date()
            inicio = datetime(fecha_obj.year, fecha_obj.month, fecha_obj.day, 3, 0, 0)
            fin = inicio + timedelta(days=1)
            query = query.filter(Domicilio.fecha_pedido >= inicio, Domicilio.fecha_pedido < fin)
        except ValueError:
            flash('Fecha inválida', 'error')
    else:
        # Por defecto, mostrar domicilios del día actual
        hoy = datetime.now().date()
        inicio = datetime(hoy.year, hoy.month, hoy.day, 3, 0, 0)
        if datetime.now().hour < 3:
            inicio = inicio - timedelta(days=1)
        fin = inicio + timedelta(days=1)
        query = query.filter(Domicilio.fecha_pedido >= inicio, Domicilio.fecha_pedido < fin)
    
    # Ordenar por fecha descendente
    domicilios = query.order_by(Domicilio.fecha_pedido.desc()).all()
    
    # Calcular estadísticas
    total_domicilios = len(domicilios)
    pendientes = sum(1 for d in domicilios if d.estado == EstadoDomicilio.PENDIENTE)
    en_preparacion = sum(1 for d in domicilios if d.estado == EstadoDomicilio.PREPARANDO)
    en_camino = sum(1 for d in domicilios if d.estado == EstadoDomicilio.EN_CAMINO)
    entregados = sum(1 for d in domicilios if d.estado == EstadoDomicilio.ENTREGADO)
    total_ventas = sum(d.total for d in domicilios if d.estado == EstadoDomicilio.ENTREGADO)
    
    return render_template("domicilios/lista_domicilios.html",
                         domicilios=domicilios,
                         total_domicilios=total_domicilios,
                         pendientes=pendientes,
                         en_preparacion=en_preparacion,
                         en_camino=en_camino,
                         entregados=entregados,
                         total_ventas=total_ventas,
                         estado_filtro=estado,
                         fecha_filtro=fecha,
                         now=datetime.now())

# =========================
# AGREGAR ESTA RUTA EN app.py
# Insertarla DESPUÉS de lista_domicilios() y ANTES de nuevo_domicilio()
# =========================

@app.route("/domicilio/<int:domicilio_id>")
@login_required
def ver_domicilio(domicilio_id):
    """
    RAZÓN: Ver detalles completos de un domicilio específico.
    Muestra información del cliente, productos, estado y permite acciones.
    """
    domicilio = Domicilio.query.get_or_404(domicilio_id)
    
    # Obtener usuarios que pueden ser repartidores (para el formulario de cambio de estado)
    repartidores = Usuario.query.filter(
        Usuario.rol.in_(['admin', 'mesero'])
    ).order_by(Usuario.nombre).all()
    
    # Obtener zonas para el formulario de edición
    zonas = ZonaDelivery.query.filter_by(activa=True).order_by(ZonaDelivery.orden).all()
    
    return render_template("domicilios/ver_domicilio.html",
                         domicilio=domicilio,
                         repartidores=repartidores,
                         zonas=zonas,
                         now=datetime.now())


@app.route("/domicilio/nuevo", methods=["GET", "POST"])
@login_required
def nuevo_domicilio():
    """
    RAZÓN: Formulario para crear un nuevo pedido a domicilio.
    """
    if request.method == "POST":
        try:
            # Datos del cliente
            cliente_nombre = request.form.get("cliente_nombre")
            cliente_telefono = request.form.get("cliente_telefono")
            cliente_direccion = request.form.get("cliente_direccion")
            cliente_barrio = request.form.get("cliente_barrio")
            cliente_referencias = request.form.get("cliente_referencias", "")
            
            # Costos
            costo_domicilio = request.form.get("costo_domicilio", 0, type=float)
            metodo_pago = request.form.get("metodo_pago", "efectivo")
            notas = request.form.get("notas", "")
            
            # Items del pedido (JSON)
            items_json = request.form.get("items_json")
            if not items_json:
                flash('Debes agregar al menos un producto', 'error')
                return redirect(url_for('nuevo_domicilio'))
            
            items_data = json.loads(items_json)
            
            if not items_data:
                flash('Debes agregar al menos un producto', 'error')
                return redirect(url_for('nuevo_domicilio'))
            
            # Calcular subtotal
            subtotal = sum(item['cantidad'] * item['precio'] for item in items_data)
            total = subtotal + costo_domicilio
            
            # Crear domicilio
            domicilio = Domicilio(
                cliente_nombre=cliente_nombre,
                cliente_telefono=cliente_telefono,
                cliente_direccion=cliente_direccion,
                cliente_barrio=cliente_barrio,
                cliente_referencias=cliente_referencias,
                subtotal=subtotal,
                costo_domicilio=costo_domicilio,
                total=total,
                metodo_pago=metodo_pago,
                notas=notas,
                tomado_por_id=current_user.id
            )
            
            db.session.add(domicilio)
            db.session.flush()  # Para obtener el ID
            
            # Agregar items
            for item_data in items_data:
                item = ItemDomicilio(
                    domicilio_id=domicilio.id,
                    item_menu_id=item_data.get('item_id'),
                    producto_nombre=item_data['nombre'],
                    cantidad=item_data['cantidad'],
                    precio_unitario=item_data['precio'],
                    notas=item_data.get('notas', '')
                )
                db.session.add(item)
            
            db.session.commit()
            
            flash(f'Domicilio #{domicilio.id} creado exitosamente - Total: ${total:,.0f}', 'success')
            return redirect(url_for('ver_domicilio', domicilio_id=domicilio.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error al crear domicilio: {str(e)}', 'error')
            return redirect(url_for('nuevo_domicilio'))
    
    # GET: Mostrar formulario
    items_menu = ItemMenu.query.filter_by(disponible=True).order_by(
        ItemMenu.categoria_id, ItemMenu.orden
    ).all()
    
    zonas = ZonaDelivery.query.filter_by(activa=True).order_by(ZonaDelivery.orden).all()
    usuarios = Usuario.query.filter(Usuario.rol.in_(['admin', 'mesero'])).order_by(Usuario.nombre).all()
    
    return render_template("domicilios/nuevo_domicilio.html",
                         items_menu=items_menu,
                         zonas=zonas,
                         usuarios=usuarios,
                         now=datetime.now())


# =========================
# NUEVA RUTA: ACTUALIZAR ESTADO ITEM COCINA
# =========================

@app.route("/domicilio/item/<int:item_id>/estado", methods=["POST"])
@login_required
def actualizar_estado_item_domicilio(item_id):
    """
    RAZÓN: Permite a cocina actualizar el estado de preparación de cada item
    """
    item = ItemDomicilio.query.get_or_404(item_id)
    nuevo_estado = request.form.get("estado")
    
    estados_validos = ['pendiente', 'preparando', 'listo']
    
    if nuevo_estado not in estados_validos:
        flash('Estado inválido', 'error')
        return redirect(url_for('ver_domicilio', domicilio_id=item.domicilio_id))
    
    item.estado_cocina = nuevo_estado
    db.session.commit()
    
    # Si todos los items están listos, actualizar estado del domicilio
    if nuevo_estado == 'listo':
        todos_listos = all(i.estado_cocina == 'listo' for i in item.domicilio.items)
        if todos_listos and item.domicilio.estado == 'preparando':
            item.domicilio.estado = EstadoDomicilio.LISTO
            item.domicilio.estado_actualizado = datetime.now()
            db.session.commit()
            flash(f'Domicilio #{item.domicilio_id} marcado como LISTO para enviar', 'success')
    
    flash(f'Estado actualizado: {nuevo_estado}', 'success')
    return redirect(url_for('ver_domicilio', domicilio_id=item.domicilio_id))



@app.route("/domicilio/<int:domicilio_id>/actualizar_estado", methods=["POST"])
@login_required
def actualizar_estado_domicilio(domicilio_id):
    """
    RAZÓN: Cambiar el estado del domicilio (pendiente → preparando → listo → en_camino → entregado)
    """
    domicilio = Domicilio.query.get_or_404(domicilio_id)
    nuevo_estado = request.form.get("estado")
    
    estados_validos = [
        EstadoDomicilio.PENDIENTE,
        EstadoDomicilio.PREPARANDO,
        EstadoDomicilio.LISTO,
        EstadoDomicilio.EN_CAMINO,
        EstadoDomicilio.ENTREGADO,
        EstadoDomicilio.CANCELADO
    ]
    
    if nuevo_estado not in estados_validos:
        flash('Estado inválido', 'error')
        return redirect(url_for('ver_domicilio', domicilio_id=domicilio_id))
    
    domicilio.estado = nuevo_estado
    domicilio.estado_actualizado = datetime.now()
    
    # Si se marca como entregado, guardar la hora de entrega
    if nuevo_estado == EstadoDomicilio.ENTREGADO:
        domicilio.fecha_entrega_real = datetime.now()
        domicilio.pagado = True
    
    # Si se asigna repartidor
    repartidor_id = request.form.get("repartidor_id", type=int)
    if repartidor_id:
        domicilio.repartidor_id = repartidor_id
    
    db.session.commit()
    
    flash(f'Estado actualizado a: {nuevo_estado}', 'success')
    return redirect(url_for('ver_domicilio', domicilio_id=domicilio_id))


@app.route("/domicilio/<int:domicilio_id>/editar", methods=["GET", "POST"])
@login_required
def editar_domicilio(domicilio_id):
    """
    RAZÓN: Editar información de un domicilio existente.
    """
    domicilio = Domicilio.query.get_or_404(domicilio_id)
    
    # Solo se puede editar si no ha sido entregado
    if domicilio.estado == EstadoDomicilio.ENTREGADO and current_user.rol != 'admin':
        flash('No se puede editar un domicilio ya entregado', 'error')
        return redirect(url_for('ver_domicilio', domicilio_id=domicilio_id))
    
    if request.method == "POST":
        try:
            # Actualizar datos del cliente
            domicilio.cliente_nombre = request.form.get("cliente_nombre")
            domicilio.cliente_telefono = request.form.get("cliente_telefono")
            domicilio.cliente_direccion = request.form.get("cliente_direccion")
            domicilio.cliente_barrio = request.form.get("cliente_barrio")
            domicilio.cliente_referencias = request.form.get("cliente_referencias", "")
            
            # Actualizar costos
            domicilio.costo_domicilio = request.form.get("costo_domicilio", 0, type=float)
            domicilio.metodo_pago = request.form.get("metodo_pago")
            domicilio.notas = request.form.get("notas", "")
            
            # Recalcular total
            domicilio.total = domicilio.subtotal + domicilio.costo_domicilio
            
            db.session.commit()
            
            flash('Domicilio actualizado exitosamente', 'success')
            return redirect(url_for('ver_domicilio', domicilio_id=domicilio_id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error al actualizar: {str(e)}', 'error')
    
    # GET
    zonas = ZonaDelivery.query.filter_by(activa=True).order_by(ZonaDelivery.orden).all()
    usuarios = Usuario.query.filter(Usuario.rol.in_(['admin', 'mesero'])).order_by(Usuario.nombre).all()
    
    return render_template("domicilios/editar_domicilio.html",
                         domicilio=domicilio,
                         zonas=zonas,
                         usuarios=usuarios)


@app.route("/domicilio/<int:domicilio_id>/cancelar", methods=["POST"])
@login_required
def cancelar_domicilio(domicilio_id):
    """
    RAZÓN: Cancelar un domicilio con motivo.
    """
    if current_user.rol not in ['admin', 'mesero']:
        flash('No tienes permisos para cancelar domicilios', 'error')
        return redirect(url_for('lista_domicilios'))
    
    domicilio = Domicilio.query.get_or_404(domicilio_id)
    
    if domicilio.estado == EstadoDomicilio.ENTREGADO:
        flash('No se puede cancelar un domicilio ya entregado', 'error')
        return redirect(url_for('ver_domicilio', domicilio_id=domicilio_id))
    
    motivo = request.form.get("motivo_cancelacion", "")
    
    domicilio.estado = EstadoDomicilio.CANCELADO
    domicilio.notas_cancelacion = motivo
    domicilio.estado_actualizado = datetime.now()
    
    db.session.commit()
    
    flash(f'Domicilio #{domicilio_id} cancelado', 'success')
    return redirect(url_for('lista_domicilios'))


@app.route("/domicilio/<int:domicilio_id>/facturar", methods=["GET", "POST"])
@login_required
def facturar_domicilio(domicilio_id):
    """
    RAZÓN: Generar factura para un domicilio entregado.
    Similar a facturar_sesion pero para domicilios.
    """
    domicilio = Domicilio.query.get_or_404(domicilio_id)
    config = ConfiguracionRestaurante.query.first()
    
    if not config:
        config = ConfiguracionRestaurante()
        db.session.add(config)
        db.session.commit()
    
    if domicilio.factura_id:
        flash('Este domicilio ya tiene una factura generada', 'error')
        return redirect(url_for('ver_factura', factura_id=domicilio.factura_id))
    
    if request.method == "POST":
        try:
            # Obtener datos del formulario
            propina = request.form.get("propina", 0, type=float)
            estado_pago = request.form.get("estado_pago", "pagada")
            fecha_vencimiento_str = request.form.get("fecha_vencimiento")
            notas_factura = request.form.get("notas", "")
            
            # Calcular totales
            subtotal = domicilio.subtotal + domicilio.costo_domicilio
            iva = 0
            total = subtotal + propina
            
            # Generar número consecutivo
            ultima_factura = Factura.query.order_by(Factura.id.desc()).first()
            if ultima_factura:
                ultimo_num = int(ultima_factura.numero_consecutivo.split('-')[1])
                nuevo_num = ultimo_num + 1
            else:
                nuevo_num = 1
            
            numero_consecutivo = f"FACT-{nuevo_num:06d}"
            
            # Convertir fecha de vencimiento
            fecha_vencimiento = None
            if fecha_vencimiento_str and estado_pago == 'pendiente':
                fecha_vencimiento = datetime.strptime(fecha_vencimiento_str, '%Y-%m-%d').date()
            
            # Crear factura (sin sesion_id porque es domicilio)
            factura = Factura(
                numero_consecutivo=numero_consecutivo,
                sesion_id=None,  # NULL para domicilios
                subtotal=subtotal,
                iva=iva,
                propina=propina,
                total=total,
                metodo_pago=domicilio.metodo_pago,
                cliente_nombre=domicilio.cliente_nombre,
                cliente_documento="",
                notas=notas_factura,
                estado_pago=estado_pago,
                fecha_vencimiento=fecha_vencimiento,
                fecha_pago_real=datetime.now() if estado_pago == 'pagada' else None,
                saldo_pendiente=total if estado_pago == 'pendiente' else 0
            )
            
            db.session.add(factura)
            db.session.flush()
            
            # Asociar factura al domicilio
            domicilio.factura_id = factura.id
            domicilio.pagado = True
            
            db.session.commit()
            
            flash(f'Factura {numero_consecutivo} generada exitosamente', 'success')
            return redirect(url_for('ver_factura', factura_id=factura.id))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error al generar factura: {str(e)}', 'error')
            return redirect(url_for('facturar_domicilio', domicilio_id=domicilio_id))
    
    # GET: Calcular fecha de vencimiento por defecto (15 días)
    fecha_vencimiento_default = (datetime.now() + timedelta(days=15)).strftime('%Y-%m-%d')
    
    return render_template("domicilios/facturar_domicilio.html",
                         domicilio=domicilio,
                         config=config,
                         datetime=datetime,
                         fecha_vencimiento_default=fecha_vencimiento_default)
# =========================
# VISTA DE COCINA PARA DOMICILIOS
# =========================

@app.route("/cocina/domicilios")
@login_required
def cocina_domicilios():
    """
    RAZÓN: Vista especial para que cocina vea items de domicilios pendientes
    """
    if current_user.rol != 'cocina':
        flash('Solo el personal de cocina puede acceder', 'error')
        return redirect(url_for('dashboard'))
    
    # Obtener domicilios activos del día
    hoy = datetime.now().date()
    inicio = datetime(hoy.year, hoy.month, hoy.day, 3, 0, 0)
    if datetime.now().hour < 3:
        inicio = inicio - timedelta(days=1)
    fin = inicio + timedelta(days=1)
    
    domicilios_activos = Domicilio.query.filter(
        Domicilio.fecha_pedido >= inicio,
        Domicilio.fecha_pedido < fin,
        Domicilio.estado.in_([
            EstadoDomicilio.PENDIENTE,
            EstadoDomicilio.PREPARANDO,
            EstadoDomicilio.LISTO
        ])
    ).order_by(Domicilio.fecha_pedido).all()
    
    return render_template("domicilios/cocina_domicilios.html",
                         domicilios=domicilios_activos,
                         now=datetime.now())


# =========================
# RUTAS DE ZONAS DE DELIVERY
# =========================

@app.route("/zonas_delivery")
@login_required
def lista_zonas_delivery():
    """
    RAZÓN: Administrar zonas de cobertura y costos de envío.
    """
    if current_user.rol != 'admin':
        flash('Solo administradores pueden gestionar zonas', 'error')
        return redirect(url_for('dashboard'))
    
    zonas = ZonaDelivery.query.order_by(ZonaDelivery.orden).all()
    
    return render_template("domicilios/zonas_delivery.html", zonas=zonas)


@app.route("/zona_delivery/nueva", methods=["GET", "POST"])
@login_required
def nueva_zona_delivery():
    """
    RAZÓN: Crear una nueva zona de delivery.
    """
    if current_user.rol != 'admin':
        flash('Solo administradores pueden crear zonas', 'error')
        return redirect(url_for('dashboard'))
    
    if request.method == "POST":
        zona = ZonaDelivery(
            nombre=request.form.get("nombre"),
            barrios=request.form.get("barrios"),
            costo_envio=request.form.get("costo_envio", type=float),
            tiempo_estimado=request.form.get("tiempo_estimado", 30, type=int),
            orden=request.form.get("orden", 0, type=int)
        )
        
        db.session.add(zona)
        db.session.commit()
        
        flash(f'Zona {zona.nombre} creada exitosamente', 'success')
        return redirect(url_for('lista_zonas_delivery'))
    
    return render_template("domicilios/nueva_zona.html")


@app.route("/zona_delivery/<int:zona_id>/editar", methods=["GET", "POST"])
@login_required
def editar_zona_delivery(zona_id):
    """
    RAZÓN: Editar una zona existente.
    """
    if current_user.rol != 'admin':
        flash('Solo administradores pueden editar zonas', 'error')
        return redirect(url_for('dashboard'))
    
    zona = ZonaDelivery.query.get_or_404(zona_id)
    
    if request.method == "POST":
        zona.nombre = request.form.get("nombre")
        zona.barrios = request.form.get("barrios")
        zona.costo_envio = request.form.get("costo_envio", type=float)
        zona.tiempo_estimado = request.form.get("tiempo_estimado", type=int)
        zona.orden = request.form.get("orden", type=int)
        db.session.commit()
        
        flash('Zona actualizada', 'success')
        return redirect(url_for('lista_zonas_delivery'))

    return render_template("domicilios/editar_zona.html", zona=zona)
@app.route("/zona_delivery/<int:zona_id>/toggle")
@login_required
def toggle_zona_delivery(zona_id):
    """
    RAZÓN: Activar/desactivar una zona.
    """
    if current_user.rol != 'admin':
        flash('Solo administradores pueden modificar zonas', 'error')
        return redirect(url_for('dashboard'))
    
    zona = ZonaDelivery.query.get_or_404(zona_id)
    zona.activa = not zona.activa
    db.session.commit()

    estado = "activada" if zona.activa else "desactivada"
    flash(f'Zona {zona.nombre} {estado}', 'success')
    return redirect(url_for('lista_zonas_delivery'))
    
"""=========================
API PARA DOMICILIOS (AJAX)
========================="""
@app.route("/api/domicilios/activos")
@login_required
def api_domicilios_activos():
    """
    RAZÓN: Endpoint para actualizar en tiempo real los domicilios activos.
    Para pantalla de cocina o repartidores.
    """
    hoy = datetime.now().date()
    inicio = datetime(hoy.year, hoy.month, hoy.day, 3, 0, 0)
    if datetime.now().hour < 3:
        inicio = inicio - timedelta(days=1)
    fin = inicio + timedelta(days=1)
    domicilios = Domicilio.query.filter(
        Domicilio.fecha_pedido >= inicio,
        Domicilio.fecha_pedido < fin,
        Domicilio.estado.in_([
            EstadoDomicilio.PENDIENTE,
            EstadoDomicilio.PREPARANDO,
            EstadoDomicilio.LISTO,
            EstadoDomicilio.EN_CAMINO
        ])
    ).order_by(Domicilio.fecha_pedido).all()

    data = []
    for d in domicilios:
        data.append({
            'id': d.id,
            'cliente': d.cliente_nombre,
            'direccion': d.cliente_direccion,
            'barrio': d.cliente_barrio,
            'total': float(d.total),
            'estado': d.estado,
            'tiempo': d.tiempo_transcurrido,
            'retrasado': d.esta_retrasado,
            'items_count': len(d.items)
        })

    return jsonify(data)

@app.route("/api/zona/calcular_costo", methods=["POST"])
@login_required
def api_calcular_costo_zona():

    barrio = request.json.get('barrio', '').strip().lower()
    zonas = ZonaDelivery.query.filter_by(activa=True).all()

    for zona in zonas:
        barrios_zona = [b.strip().lower() for b in zona.lista_barrios]
        if barrio in barrios_zona:
            return jsonify({
                'success': True,
                'zona': zona.nombre,
                'costo': float(zona.costo_envio),
                'tiempo_estimado': zona.tiempo_estimado
            })

    # Si no se encuentra el barrio, devolver costo por defecto
    return jsonify({
        'success': False,
        'message': 'Barrio no encontrado en zonas de cobertura',
        'costo': 3000,  # Costo por defecto
        'tiempo_estimado': 30
    })



    # =========================
    # EJECUCIÓN
    # =========================
if __name__ == "__main__":
    init_db()
    