// Modelos de datos del Sistema Seguro de Turnos IESS para Afiliados

class UserModel {
  final String cedula;
  final String nombres;
  final String rol;
  final String? email;
  final String? telefono;
  final String establecimientoAsignado;
  final bool debeCambiarClave;
  final String? fechaNacimiento;

  UserModel({
    required this.cedula,
    required this.nombres,
    required this.rol,
    this.email,
    this.telefono,
    this.establecimientoAsignado = '',
    this.debeCambiarClave = false,
    this.fechaNacimiento,
  });

  factory UserModel.fromJson(Map<String, dynamic> json) {
    return UserModel(
      cedula: json['cedula']?.toString() ?? '',
      nombres: json['nombres']?.toString() ?? '',
      rol: json['rol']?.toString() ?? '',
      email: json['email']?.toString(),
      telefono: json['telefono']?.toString(),
      establecimientoAsignado: json['establecimiento_asignado']?.toString() ?? '',
      debeCambiarClave: json['debe_cambiar_clave'] == true,
      fechaNacimiento: json['fecha_nacimiento']?.toString(),
    );
  }

  Map<String, dynamic> toJson() => {
        'cedula': cedula,
        'nombres': nombres,
        'rol': rol,
        'email': email,
        'telefono': telefono,
        'establecimiento_asignado': establecimientoAsignado,
        'debe_cambiar_clave': debeCambiarClave,
        'fecha_nacimiento': fechaNacimiento,
      };
}

class DelegacionModel {
  final int id;
  final String beneficiarioCedula;
  final String beneficiarioNombre;
  final String tipoVinculo; // 'HIJO_MENOR' | 'ADULTO_AUTORIZADO'
  final bool activo;
  final String? creadoEn;

  DelegacionModel({
    required this.id,
    required this.beneficiarioCedula,
    required this.beneficiarioNombre,
    required this.tipoVinculo,
    required this.activo,
    this.creadoEn,
  });

  factory DelegacionModel.fromJson(Map<String, dynamic> json) {
    return DelegacionModel(
      id: json['id'] is int ? json['id'] : int.tryParse(json['id'].toString()) ?? 0,
      beneficiarioCedula: json['beneficiario_cedula']?.toString() ?? '',
      beneficiarioNombre: json['beneficiario_nombre']?.toString() ?? '',
      tipoVinculo: json['tipo_vinculo']?.toString() ?? '',
      activo: json['activo'] == true,
      creadoEn: json['creado_en']?.toString(),
    );
  }
}

class TurnoSlotModel {
  final String medicoCedula;
  final String medicoNombre;
  final String establecimiento;
  final String especialidad;
  final String fecha;
  final String hora;
  final bool disponible;
  final String motivoNoDisponible;

  TurnoSlotModel({
    required this.medicoCedula,
    required this.medicoNombre,
    required this.establecimiento,
    required this.especialidad,
    required this.fecha,
    required this.hora,
    required this.disponible,
    this.motivoNoDisponible = '',
  });

  factory TurnoSlotModel.fromJson(Map<String, dynamic> json) {
    return TurnoSlotModel(
      medicoCedula: json['medico_cedula']?.toString() ?? '',
      medicoNombre: json['medico_nombre']?.toString() ?? '',
      establecimiento: json['establecimiento']?.toString() ?? '',
      especialidad: json['especialidad']?.toString() ?? '',
      fecha: json['fecha']?.toString() ?? '',
      hora: json['hora']?.toString() ?? '',
      disponible: json['disponible'] != false,
      motivoNoDisponible: json['motivo_no_disponible']?.toString() ?? '',
    );
  }
}

class TurnoModel {
  final int id;
  final String afiliadoCedula;
  final String afiliadoNombre;
  final String medicoCedula;
  final String medicoNombre;
  final String establecimiento;
  final String especialidad;
  final String fecha;
  final String hora;
  final String estado; // 'RESERVADO' | 'CANCELADO' | 'ATENDIDO'
  final bool puedeModificar24h;

  TurnoModel({
    required this.id,
    required this.afiliadoCedula,
    required this.afiliadoNombre,
    required this.medicoCedula,
    required this.medicoNombre,
    required this.establecimiento,
    required this.especialidad,
    required this.fecha,
    required this.hora,
    required this.estado,
    required this.puedeModificar24h,
  });

  factory TurnoModel.fromJson(Map<String, dynamic> json) {
    return TurnoModel(
      id: json['id'] is int ? json['id'] : int.tryParse(json['id'].toString()) ?? 0,
      afiliadoCedula: json['afiliado_cedula']?.toString() ?? '',
      afiliadoNombre: json['afiliado_nombre']?.toString() ?? '',
      medicoCedula: json['medico_cedula']?.toString() ?? '',
      medicoNombre: json['medico_nombre']?.toString() ?? '',
      establecimiento: json['establecimiento']?.toString() ?? '',
      especialidad: json['especialidad']?.toString() ?? '',
      fecha: json['fecha']?.toString() ?? '',
      hora: json['hora']?.toString() ?? '',
      estado: json['estado']?.toString() ?? 'RESERVADO',
      puedeModificar24h: json['puede_modificar_24h'] == true,
    );
  }
}

class NotificacionModel {
  final int id;
  final String tipo;
  final String canal;
  final String establecimiento;
  final String especialidad;
  final String fecha;
  final String hora;
  final String estadoTurno;
  final String enlaceRelativo;
  final String mensaje;
  final String? creadaEn;

  NotificacionModel({
    required this.id,
    required this.tipo,
    required this.canal,
    required this.establecimiento,
    required this.especialidad,
    required this.fecha,
    required this.hora,
    required this.estadoTurno,
    required this.enlaceRelativo,
    required this.mensaje,
    this.creadaEn,
  });

  factory NotificacionModel.fromJson(Map<String, dynamic> json) {
    return NotificacionModel(
      id: json['id'] is int ? json['id'] : int.tryParse(json['id'].toString()) ?? 0,
      tipo: json['tipo']?.toString() ?? '',
      canal: json['canal']?.toString() ?? '',
      establecimiento: json['establecimiento']?.toString() ?? '',
      especialidad: json['especialidad']?.toString() ?? '',
      fecha: json['fecha']?.toString() ?? '',
      hora: json['hora']?.toString() ?? '',
      estadoTurno: json['estado_turno']?.toString() ?? '',
      enlaceRelativo: json['enlace_relativo']?.toString() ?? '',
      mensaje: json['mensaje']?.toString() ?? '',
      creadaEn: json['creada_en']?.toString(),
    );
  }
}

class UserSessionModel {
  final String id;
  final String ip;
  final String userAgent;
  final bool mfaVerificado;
  final bool activa;
  final String creadaEn;
  final String ultimaActividad;
  final String expiraEn;
  final bool esActual;

  UserSessionModel({
    required this.id,
    required this.ip,
    required this.userAgent,
    required this.mfaVerificado,
    required this.activa,
    required this.creadaEn,
    required this.ultimaActividad,
    required this.expiraEn,
    required this.esActual,
  });

  factory UserSessionModel.fromJson(Map<String, dynamic> json) {
    return UserSessionModel(
      id: json['id']?.toString() ?? '',
      ip: json['ip']?.toString() ?? 'Local',
      userAgent: json['user_agent']?.toString() ?? '',
      mfaVerificado: json['mfa_verificado'] == true,
      activa: json['activa'] == true,
      creadaEn: json['creada_en']?.toString() ?? '',
      ultimaActividad: json['ultima_actividad']?.toString() ?? '',
      expiraEn: json['expira_en']?.toString() ?? '',
      esActual: json['es_actual'] == true,
    );
  }
}
