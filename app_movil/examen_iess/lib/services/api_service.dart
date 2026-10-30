import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;
import '../models/models.dart';

class ApiException implements Exception {
  final String message;
  final int? statusCode;
  final dynamic data;

  ApiException(this.message, {this.statusCode, this.data});

  @override
  String toString() => message;
}

class ApiService {
  static final ApiService _instance = ApiService._internal();
  factory ApiService() => _instance;
  ApiService._internal() {
    _initDefaultBaseUrl();
  }

  void _initDefaultBaseUrl() {
    try {
      if (Platform.isAndroid) {
        _baseUrl = 'http://10.0.2.2:8000/api';
      } else {
        _baseUrl = 'http://localhost:8000/api';
      }
    } catch (_) {
      _baseUrl = 'http://localhost:8000/api';
    }
  }

  late String _baseUrl;
  String get baseUrl => _baseUrl;
  set baseUrl(String url) {
    var clean = url.trim();
    if (clean.endsWith('/')) {
      clean = clean.substring(0, clean.length - 1);
    }
    if (!clean.endsWith('/api')) {
      clean = '$clean/api';
    }
    _baseUrl = clean;
  }

  String? accessToken;
  String? refreshToken;
  String? sessionId;
  UserModel? currentUser;

  bool get isAuthenticated => accessToken != null && currentUser != null;

  Map<String, String> _buildHeaders({bool includeAuth = true}) {
    final headers = <String, String>{
      'Content-Type': 'application/json',
      'Accept': 'application/json',
    };
    if (includeAuth && accessToken != null) {
      headers['Authorization'] = 'Bearer $accessToken';
    }
    return headers;
  }

  Future<dynamic> _handleResponse(http.Response response) async {
    dynamic jsonBody;
    try {
      if (response.body.isNotEmpty) {
        jsonBody = jsonDecode(utf8.decode(response.bodyBytes));
      }
    } catch (_) {
      jsonBody = response.body;
    }

    if (response.statusCode >= 200 && response.statusCode < 300) {
      return jsonBody;
    }

    String msg = 'Error en la solicitud (${response.statusCode})';
    if (jsonBody is Map<String, dynamic>) {
      if (jsonBody.containsKey('detail')) {
        msg = jsonBody['detail'].toString();
      } else if (jsonBody.containsKey('mensaje')) {
        msg = jsonBody['mensaje'].toString();
      } else if (jsonBody.containsKey('non_field_errors')) {
        final err = jsonBody['non_field_errors'];
        msg = err is List && err.isNotEmpty ? err.first.toString() : err.toString();
      } else if (jsonBody.isNotEmpty) {
        final firstKey = jsonBody.keys.first;
        final firstVal = jsonBody.values.first;
        if (firstVal is List && firstVal.isNotEmpty) {
          msg = '$firstKey: ${firstVal.first}';
        } else {
          msg = '$firstKey: $firstVal';
        }
      }
    } else if (jsonBody is String && jsonBody.isNotEmpty) {
      if (jsonBody.contains('<title>') && jsonBody.contains('</title>')) {
        final match = RegExp(r'<title>(.*?)</title>', caseSensitive: false).firstMatch(jsonBody);
        if (match != null) {
          msg = 'Error del servidor: ${match.group(1)}';
        }
      } else if (jsonBody.length < 200) {
        msg = jsonBody;
      }
    }

    throw ApiException(msg, statusCode: response.statusCode, data: jsonBody);
  }

  Future<dynamic> _get(String path, {Map<String, dynamic>? queryParams}) async {
    var uri = Uri.parse('$_baseUrl$path');
    if (queryParams != null && queryParams.isNotEmpty) {
      final sanitized = <String, String>{};
      queryParams.forEach((k, v) {
        if (v != null && v.toString().isNotEmpty) {
          sanitized[k] = v.toString();
        }
      });
      uri = uri.replace(queryParameters: sanitized);
    }

    var resp = await http.get(uri, headers: _buildHeaders());

    // Auto-refresh JWT if 401
    if (resp.statusCode == 401 && refreshToken != null && !path.contains('/auth/')) {
      final refreshed = await _refreshAccessToken();
      if (refreshed) {
        resp = await http.get(uri, headers: _buildHeaders());
      }
    }

    return _handleResponse(resp);
  }

  Future<dynamic> _post(String path, {dynamic body, bool includeAuth = true}) async {
    final uri = Uri.parse('$_baseUrl$path');
    final encoded = body != null ? jsonEncode(body) : null;

    var resp = await http.post(uri, headers: _buildHeaders(includeAuth: includeAuth), body: encoded);

    if (resp.statusCode == 401 && refreshToken != null && !path.contains('/auth/')) {
      final refreshed = await _refreshAccessToken();
      if (refreshed) {
        resp = await http.post(uri, headers: _buildHeaders(includeAuth: includeAuth), body: encoded);
      }
    }

    return _handleResponse(resp);
  }

  Future<dynamic> _delete(String path) async {
    final uri = Uri.parse('$_baseUrl$path');
    var resp = await http.delete(uri, headers: _buildHeaders());

    if (resp.statusCode == 401 && refreshToken != null && !path.contains('/auth/')) {
      final refreshed = await _refreshAccessToken();
      if (refreshed) {
        resp = await http.delete(uri, headers: _buildHeaders());
      }
    }

    return _handleResponse(resp);
  }

  Future<bool> _refreshAccessToken() async {
    if (refreshToken == null) return false;
    try {
      final uri = Uri.parse('$_baseUrl/auth/refresh/');
      final resp = await http.post(
        uri,
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'refresh': refreshToken}),
      );
      if (resp.statusCode == 200) {
        final data = jsonDecode(resp.body);
        accessToken = data['access'];
        return true;
      }
    } catch (_) {}
    clearSession();
    return false;
  }

  void clearSession() {
    accessToken = null;
    refreshToken = null;
    sessionId = null;
    currentUser = null;
  }

  // ==========================================
  // AUTENTICACIÓN Y MFA (REQ. 107)
  // ==========================================

  Future<Map<String, dynamic>> login(String cedula, String password) async {
    final res = await _post('/auth/login/', body: {
      'cedula': cedula.trim(),
      'password': password,
    }, includeAuth: false);
    return Map<String, dynamic>.from(res);
  }

  Future<UserModel> verifyOtp(String cedula, String otp) async {
    final res = await _post('/auth/verify-otp/', body: {
      'cedula': cedula.trim(),
      'otp': otp.trim(),
    }, includeAuth: false);

    final userMap = Map<String, dynamic>.from(res['user'] ?? {});
    final user = UserModel.fromJson(userMap);

    // REGLA CLAVE: Solo Afiliados en la App Móvil
    if (user.rol != 'AFILIADO') {
      clearSession();
      throw ApiException(
        'Acceso restringido: Esta app móvil es de uso exclusivo para AFILIADOS del IESS. '
        'El personal institucional (Recepción, Médicos, Soporte y Admin) debe ingresar por el aplicativo web.',
        statusCode: 403,
      );
    }

    accessToken = res['access']?.toString();
    refreshToken = res['refresh']?.toString();
    sessionId = res['session_id']?.toString();
    currentUser = user;

    return user;
  }

  Future<void> changePassword(String newPassword, {String? currentPassword}) async {
    final body = <String, dynamic>{
      'new_password': newPassword,
    };
    if (currentPassword != null && currentPassword.isNotEmpty) {
      body['current_password'] = currentPassword;
    }
    await _post('/auth/change-password/', body: body);
    if (currentUser != null) {
      currentUser = UserModel(
        cedula: currentUser!.cedula,
        nombres: currentUser!.nombres,
        rol: currentUser!.rol,
        email: currentUser!.email,
        telefono: currentUser!.telefono,
        establecimientoAsignado: currentUser!.establecimientoAsignado,
        debeCambiarClave: false,
        fechaNacimiento: currentUser!.fechaNacimiento,
      );
    }
  }

  Future<void> logout() async {
    try {
      if (accessToken != null) {
        await _post('/auth/logout/', body: {});
      }
    } catch (_) {}
    clearSession();
  }

  Future<List<UserSessionModel>> getActiveSessions() async {
    final res = await _get('/auth/sessions/');
    if (res is List) {
      return res.map((e) => UserSessionModel.fromJson(Map<String, dynamic>.from(e))).toList();
    }
    return [];
  }

  Future<void> revokeSession(String sessionUuid) async {
    await _delete('/auth/sessions/$sessionUuid/');
  }

  // ==========================================
  // REGISTRO DE AFILIADOS (REQ. 102)
  // ==========================================

  Future<Map<String, dynamic>> consultarPadron(String cedula) async {
    final res = await _post('/auth/registro/consultar-cedula/', body: {
      'cedula': cedula.trim(),
    }, includeAuth: false);
    return Map<String, dynamic>.from(res);
  }

  Future<Map<String, dynamic>> solicitarOtpRegistro({
    required String cedula,
    required String email,
    required String telefono,
    required String password,
  }) async {
    final res = await _post('/auth/registro/solicitar-otp/', body: {
      'cedula': cedula.trim(),
      'email': email.trim().toLowerCase(),
      'telefono': telefono.trim(),
      'password': password,
    }, includeAuth: false);
    return Map<String, dynamic>.from(res);
  }

  Future<Map<String, dynamic>> confirmarOtpRegistro({
    required String cedula,
    required String otp,
  }) async {
    final res = await _post('/auth/registro/confirmar-otp/', body: {
      'cedula': cedula.trim(),
      'otp': otp.trim(),
    }, includeAuth: false);
    return Map<String, dynamic>.from(res);
  }

  // ==========================================
  // TURNOS Y DISPONIBILIDAD (REQ. 101)
  // ==========================================

  Future<Map<String, dynamic>> getDisponibilidad({
    String? establecimiento,
    String? especialidad,
    String? fecha,
  }) async {
    final q = <String, dynamic>{};
    if (establecimiento != null) q['establecimiento'] = establecimiento;
    if (especialidad != null) q['especialidad'] = especialidad;
    if (fecha != null) q['fecha'] = fecha;

    final res = await _get('/turnos/disponibilidad/', queryParams: q);
    return Map<String, dynamic>.from(res);
  }

  Future<TurnoModel> reservarTurno({
    String? beneficiarioCedula,
    required String medicoCedula,
    required String establecimiento,
    required String especialidad,
    required String fecha,
    required String hora,
  }) async {
    final res = await _post('/turnos/reservar/', body: {
      if (beneficiarioCedula != null && beneficiarioCedula.isNotEmpty)
        'beneficiario_cedula': beneficiarioCedula,
      'medico_cedula': medicoCedula,
      'establecimiento': establecimiento,
      'especialidad': especialidad,
      'fecha': fecha,
      'hora': hora,
    });
    final turnoData = res['turno'] ?? res;
    return TurnoModel.fromJson(Map<String, dynamic>.from(turnoData));
  }

  Future<List<TurnoModel>> getMisTurnos(String beneficiarioCedula) async {
    final res = await _get('/turnos/mis-turnos/', queryParams: {
      'beneficiario_cedula': beneficiarioCedula,
    });
    if (res is List) {
      return res.map((e) => TurnoModel.fromJson(Map<String, dynamic>.from(e))).toList();
    }
    return [];
  }

  Future<TurnoModel> getTurnoDetalle(int turnoId) async {
    final res = await _get('/turnos/$turnoId/');
    return TurnoModel.fromJson(Map<String, dynamic>.from(res));
  }

  Future<void> cancelarTurno(int turnoId) async {
    await _post('/turnos/$turnoId/cancelar/', body: {});
  }

  Future<TurnoModel> reprogramarTurno(
    int turnoId, {
    required String fecha,
    required String hora,
    String? medicoCedula,
  }) async {
    final body = <String, dynamic>{
      'fecha': fecha,
      'hora': hora,
    };
    if (medicoCedula != null && medicoCedula.isNotEmpty) {
      body['medico_cedula'] = medicoCedula;
    }
    final res = await _post('/turnos/$turnoId/reprogramar/', body: body);
    final turnoData = res['turno'] ?? res;
    return TurnoModel.fromJson(Map<String, dynamic>.from(turnoData));
  }

  // ==========================================
  // DELEGACIÓN FAMILIAR (ANTI-BOLA - REQ. 106)
  // ==========================================

  Future<List<DelegacionModel>> getDelegaciones() async {
    final res = await _get('/delegaciones/');
    if (res is List) {
      return res.map((e) => DelegacionModel.fromJson(Map<String, dynamic>.from(e))).toList();
    }
    return [];
  }

  Future<Map<String, dynamic>> solicitarDelegacion(String titularCedula) async {
    final res = await _post('/delegaciones/solicitar/', body: {
      'titular_cedula': titularCedula.trim(),
    });
    return Map<String, dynamic>.from(res);
  }

  Future<DelegacionModel> confirmarDelegacionOtp(String titularCedula, String otp) async {
    final res = await _post('/delegaciones/confirmar-otp/', body: {
      'titular_cedula': titularCedula.trim(),
      'otp': otp.trim(),
    });
    final dData = res['delegacion'] ?? res;
    return DelegacionModel.fromJson(Map<String, dynamic>.from(dData));
  }

  // ==========================================
  // NOTIFICACIONES (REQ. 109)
  // ==========================================

  Future<List<NotificacionModel>> getNotificaciones() async {
    final res = await _get('/notificaciones/');
    if (res is List) {
      return res.map((e) => NotificacionModel.fromJson(Map<String, dynamic>.from(e))).toList();
    }
    return [];
  }
}

