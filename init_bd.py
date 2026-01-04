"""
Script de inicialización de la base de datos
Ejecutar con: python init_db.py
"""

from app import CategoriaGasto, Presupuesto, app, db, Usuario, Mesa, Sesion

def init_database():
    with app.app_context():
        print("🔧 Creando/actualizando tablas de base de datos...")
        db.create_all()
        
        # Crear usuarios por defecto
        usuarios_default = [
            {
                'username': 'admin',
                'password': 'admin123',
                'nombre': 'Administrador',
                'rol': 'admin'
            },
            {
                'username': 'mesero1',
                'password': 'mesero123',
                'nombre': 'Mesero 1',
                'rol': 'mesero'
            },
            {
                'username': 'mesero2',
                'password': 'mesero123',
                'nombre': 'Mesero 2',
                'rol': 'mesero'
            },
            {
                'username': 'cocina',
                'password': 'cocina123',
                'nombre': 'Cocina',
                'rol': 'cocina'
            }
        ]
        
        print("\n👥 Creando usuarios...")
        for user_data in usuarios_default:
            if not Usuario.query.filter_by(username=user_data['username']).first():
                usuario = Usuario(
                    username=user_data['username'],
                    nombre=user_data['nombre'],
                    rol=user_data['rol']
                )
                usuario.set_password(user_data['password'])
                db.session.add(usuario)
                print(f"   ✓ Usuario creado: {user_data['username']} (rol: {user_data['rol']})")
            else:
                print(f"   ⚠ Usuario ya existe: {user_data['username']}")
        
        # Crear mesas
        print("\n🪑 Creando mesas...")
        if Mesa.query.count() == 0:
            for i in range(1, 11):
                mesa = Mesa(numero=i, capacidad=4)
                db.session.add(mesa)
            print(f"   ✓ Creadas 10 mesas (1-10)")
        else:
            print(f"   ⚠ Ya existen {Mesa.query.count()} mesas")
        
        # Guardar cambios

        if Presupuesto.query.count() == 0:
            from datetime import datetime
            mes_actual = datetime.now().month
            anio_actual = datetime.now().year
            
            # Obtener categorías
            cat_ingredientes = CategoriaGasto.query.filter_by(nombre='Ingredientes y Materia Prima').first()
            cat_salarios = CategoriaGasto.query.filter_by(nombre='Salarios y Nómina').first()
            cat_servicios = CategoriaGasto.query.filter_by(nombre='Servicios Públicos').first()
            
            presupuestos_default = []
            
            if cat_ingredientes:
                presupuestos_default.append(Presupuesto(
                    categoria_id=cat_ingredientes.id,
                    monto_limite=2000000,  # $2,000,000
                    periodo='mensual',
                    mes=mes_actual,
                    anio=anio_actual,
                    alerta_porcentaje=80
                ))
            
            if cat_salarios:
                presupuestos_default.append(Presupuesto(
                    categoria_id=cat_salarios.id,
                    monto_limite=3000000,  # $3,000,000
                    periodo='mensual',
                    mes=mes_actual,
                    anio=anio_actual,
                    alerta_porcentaje=90
                ))
            
            if cat_servicios:
                presupuestos_default.append(Presupuesto(
                    categoria_id=cat_servicios.id,
                    monto_limite=500000,  # $500,000
                    periodo='mensual',
                    mes=mes_actual,
                    anio=anio_actual,
                    alerta_porcentaje=75
                ))
            
            for p in presupuestos_default:
                db.session.add(p)
            
            print("Presupuestos de ejemplo creados")
        
        db.session.commit()
        print("Base de datos inicializada correctamente")
        print("\n✅ Base de datos inicializada correctamente!")
        print("\n📊 NUEVO: Sistema de sesiones activado")
        print("   • Cada grupo de clientes tiene su propia sesión")
        print("   • Dashboard más compacto y eficiente")
        print("   • Mejor separación de turnos por mesa")
        print("\n📋 Usuarios disponibles:")
        print("   • admin / admin123 (Administrador)")
        print("   • mesero1 / mesero123 (Mesero)")
        print("   • mesero2 / mesero123 (Mesero)")
        print("   • cocina / cocina123 (Cocina)")
        print("\n⚠️  IMPORTANTE: Cambia estas contraseñas en producción!")
        print("\n🎯 Próximo paso: python app.py\n")

if __name__ == "__main__":
    init_database()