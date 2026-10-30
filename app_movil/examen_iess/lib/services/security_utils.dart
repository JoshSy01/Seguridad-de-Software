// Utilidades de Seguridad del Sistema IESS
// Implementa la validación oficial de Cédula Ecuatoriana (Módulo 10)
// y las reglas de contraseñas robustas (Req. 107).

class PasswordValidationResult {
  final bool largoOk;
  final bool usaCedula;
  final bool usaFecha;

  const PasswordValidationResult({
    required this.largoOk,
    required this.usaCedula,
    required this.usaFecha,
  });

  bool get esValida => largoOk && !usaCedula && !usaFecha;
}

/// Algoritmo oficial de validación de Cédula de Identidad Ecuatoriana (Módulo 10):
/// - 10 dígitos numéricos exactos.
/// - No permite dígitos repetidos triviales (ej. 0000000000, 1111111111).
/// - Código de provincia válido: 01 a 24, o 30 (ecuatorianos en el exterior).
/// - Tercer dígito menor a 6 (personas naturales: 0 a 5).
/// - Verificación del décimo dígito mediante Módulo 10 con coeficientes [2,1,2,1,2,1,2,1,2].
bool esCedulaEcuatorianaValida(String? cedula) {
  if (cedula == null) return false;
  final ced = cedula.trim();
  if (!RegExp(r'^\d{10}$').hasMatch(ced)) return false;

  // Rechazar dígitos repetidos
  if (RegExp(r'^(\d)\1{9}$').hasMatch(ced)) return false;

  final provincia = int.tryParse(ced.substring(0, 2)) ?? 0;
  if (!((provincia >= 1 && provincia <= 24) || provincia == 30)) {
    return false;
  }

  final tercerDigito = int.tryParse(ced.substring(2, 3)) ?? 9;
  if (tercerDigito >= 6) {
    return false;
  }

  const coeficientes = [2, 1, 2, 1, 2, 1, 2, 1, 2];
  int suma = 0;
  for (int i = 0; i < 9; i++) {
    int valor = (int.tryParse(ced.substring(i, i + 1)) ?? 0) * coeficientes[i];
    if (valor >= 10) valor -= 9;
    suma += valor;
  }

  final digitoVerificador = (10 - (suma % 10)) % 10;
  final decimoDigito = int.tryParse(ced.substring(9, 10)) ?? -1;

  return digitoVerificador == decimoDigito;
}

/// Comprueba si la contraseña contiene la fecha de nacimiento en diversos formatos
bool contieneFechaNacimiento(String password, String? fechaIso) {
  if (password.isEmpty || fechaIso == null || fechaIso.isEmpty) return false;
  final parts = fechaIso.split('-');
  if (parts.length != 3) return false;

  final yyyy = parts[0];
  final mm = parts[1];
  final dd = parts[2];

  final patrones = [
    '$yyyy$mm$dd',
    '$dd$mm$yyyy',
    '$yyyy-$mm-$dd',
    '$dd-$mm-$yyyy',
    '$yyyy/$mm/$dd',
    '$dd/$mm/$yyyy',
  ];

  for (final p in patrones) {
    if (password.contains(p)) return true;
  }
  return false;
}

/// Validador estricto Req. 107
PasswordValidationResult validarPoliticaClave(
  String password,
  String? cedula,
  String? fechaIso,
) {
  final largoOk = password.length >= 12;
  final usaCedula = cedula != null && cedula.isNotEmpty && password.contains(cedula);
  final usaFecha = contieneFechaNacimiento(password, fechaIso);

  return PasswordValidationResult(
    largoOk: largoOk,
    usaCedula: usaCedula,
    usaFecha: usaFecha,
  );
}
