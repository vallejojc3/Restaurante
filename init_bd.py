"""
Script de inicialización de la base de datos
Ejecutar con: python init_db.py
"""

from app import app, db, Usuario, Mesa, Sesion

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
        db.session.commit()
        
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