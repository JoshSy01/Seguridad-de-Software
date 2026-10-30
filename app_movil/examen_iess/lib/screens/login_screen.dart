import 'package:flutter/material.dart';
import '../services/api_service.dart';
import '../services/security_utils.dart';
import 'dashboard_afiliado_screen.dart';
import 'registro_afiliado_screen.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _api = ApiService();

  // Estados de Login
  final _cedulaController = TextEditingController();
  final _passwordController = TextEditingController();
  final _otpController = TextEditingController();

  bool _isOtpStep = false;
  String _debugOtp = '';
  bool _loading = false;
  String? _errorMessage;
  String? _successMessage;

  // Estados para cambio obligatorio de contraseña
  final _newPasswordController = TextEditingController();
  final _confirmPasswordController = TextEditingController();

  @override
  void dispose() {
    _cedulaController.dispose();
    _passwordController.dispose();
    _otpController.dispose();
    _newPasswordController.dispose();
    _confirmPasswordController.dispose();
    super.dispose();
  }

  void _showServerConfigDialog() {
    final controller = TextEditingController(text: _api.baseUrl);
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Configurar Servidor Backend', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Seleccione o ingrese la URL base de la API Django:',
              style: TextStyle(fontSize: 12, color: Colors.black54),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: controller,
              decoration: const InputDecoration(
                labelText: 'URL API',
                border: OutlineInputBorder(),
                prefixIcon: Icon(Icons.link, size: 20),
              ),
              style: const TextStyle(fontSize: 13),
            ),
            const SizedBox(height: 12),
            Wrap(
              spacing: 6,
              children: [
                ActionChip(
                  label: const Text('Localhost (Desktop)', style: TextStyle(fontSize: 11)),
                  onPressed: () => controller.text = 'http://localhost:8000/api',
                ),
                ActionChip(
                  label: const Text('10.0.2.2 (Emulador Android)', style: TextStyle(fontSize: 11)),
                  onPressed: () => controller.text = 'http://10.0.2.2:8000/api',
                ),
              ],
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Cancelar'),
          ),
          ElevatedButton(
            style: ElevatedButton.styleFrom(backgroundColor: const Color(0xFF0B3B60)),
            onPressed: () {
              _api.baseUrl = controller.text.trim();
              Navigator.pop(ctx);
              ScaffoldMessenger.of(context).showSnackBar(
                SnackBar(content: Text('Servidor configurado: ${_api.baseUrl}')),
              );
            },
            child: const Text('Guardar', style: TextStyle(color: Colors.white)),
          ),
        ],
      ),
    );
  }

  Future<void> _handleLogin() async {
    final cedula = _cedulaController.text.trim();
    final password = _passwordController.text;

    if (!esCedulaEcuatorianaValida(cedula)) {
      setState(() => _errorMessage = 'La cédula ingresada no cumple con el algoritmo Módulo 10 del Registro Civil.');
      return;
    }

    setState(() {
      _loading = true;
      _errorMessage = null;
      _successMessage = null;
    });

    try {
      final res = await _api.login(cedula, password);
      setState(() {
        _isOtpStep = true;
        _debugOtp = res['debug_otp']?.toString() ?? '';
        _otpController.text = _debugOtp; // Facilitar prueba en entorno local
        _successMessage = 'Código MFA enviado. Ingrese el OTP de 6 dígitos.';
      });
    } on ApiException catch (e) {
      setState(() => _errorMessage = e.message);
    } catch (e) {
      setState(() => _errorMessage = 'No se pudo conectar al backend: $e');
    } finally {
      setState(() => _loading = false);
    }
  }

  Future<void> _handleVerifyOtp() async {
    final cedula = _cedulaController.text.trim();
    final otp = _otpController.text.trim();

    if (otp.length != 6) {
      setState(() => _errorMessage = 'El código OTP debe ser de 6 dígitos.');
      return;
    }

    setState(() {
      _loading = true;
      _errorMessage = null;
    });

    try {
      final user = await _api.verifyOtp(cedula, otp);

      if (!mounted) return;

      if (user.debeCambiarClave) {
        _showForceChangePasswordDialog();
      } else {
        Navigator.pushReplacement(
          context,
          MaterialPageRoute(builder: (_) => const DashboardAfiliadoScreen()),
        );
      }
    } on ApiException catch (e) {
      setState(() => _errorMessage = e.message);
    } catch (e) {
      setState(() => _errorMessage = 'Error al validar OTP: $e');
    } finally {
      setState(() => _loading = false);
    }
  }

  void _showForceChangePasswordDialog() {
    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (ctx) => StatefulBuilder(
        builder: (context, setDialogState) {
          final newPwd = _newPasswordController.text;
          final val = validarPoliticaClave(
            newPwd,
            _api.currentUser?.cedula,
            _api.currentUser?.fechaNacimiento,
          );
          final passwordsMatch = newPwd == _confirmPasswordController.text && newPwd.isNotEmpty;

          return AlertDialog(
            title: const Row(
              children: [
                Icon(Icons.shield_outlined, color: Color(0xFF0B3B60)),
                SizedBox(width: 8),
                Text('Cambio Obligatorio de Clave', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
              ],
            ),
            content: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'Por política de seguridad institucional (Req. 107), debe definir una nueva contraseña robusta antes de acceder al portal móvil.',
                    style: TextStyle(fontSize: 12, color: Colors.black54),
                  ),
                  const SizedBox(height: 12),
                  TextField(
                    controller: _newPasswordController,
                    obscureText: true,
                    decoration: const InputDecoration(
                      labelText: 'Nueva Contraseña Segura',
                      border: OutlineInputBorder(),
                    ),
                    onChanged: (_) => setDialogState(() {}),
                  ),
                  const SizedBox(height: 10),
                  TextField(
                    controller: _confirmPasswordController,
                    obscureText: true,
                    decoration: const InputDecoration(
                      labelText: 'Confirmar Nueva Contraseña',
                      border: OutlineInputBorder(),
                    ),
                    onChanged: (_) => setDialogState(() {}),
                  ),
                  const SizedBox(height: 12),
                  Container(
                    padding: const EdgeInsets.all(10),
                    decoration: BoxDecoration(
                      color: Colors.grey.shade50,
                      borderRadius: BorderRadius.circular(8),
                      border: Border.all(color: Colors.grey.shade300),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        _buildRuleItem('Mínimo 12 caracteres', val.largoOk),
                        _buildRuleItem('Sin número de cédula', !val.usaCedula),
                        _buildRuleItem('Sin fecha de nacimiento', !val.usaFecha),
                        _buildRuleItem('Contraseñas coinciden', passwordsMatch),
                      ],
                    ),
                  ),
                ],
              ),
            ),
            actions: [
              ElevatedButton(
                style: ElevatedButton.styleFrom(backgroundColor: const Color(0xFF0B3B60)),
                onPressed: (!val.esValida || !passwordsMatch)
                    ? null
                    : () async {
                        try {
                          await _api.changePassword(
                            newPwd,
                            currentPassword: _passwordController.text,
                          );
                          if (!ctx.mounted) return;
                          Navigator.pop(ctx);
                          if (!context.mounted) return;
                          Navigator.pushReplacement(
                            context,
                            MaterialPageRoute(builder: (_) => const DashboardAfiliadoScreen()),
                          );
                        } on ApiException catch (e) {
                          if (ctx.mounted) {
                            ScaffoldMessenger.of(ctx).showSnackBar(SnackBar(content: Text(e.message)));
                          }
                        }
                      },
                child: const Text('Actualizar y Entrar', style: TextStyle(color: Colors.white)),
              ),
            ],
          );
        },
      ),
    );
  }

  Widget _buildRuleItem(String text, bool ok) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(
        children: [
          Icon(ok ? Icons.check_circle : Icons.radio_button_unchecked, size: 14, color: ok ? Colors.green : Colors.grey),
          const SizedBox(width: 6),
          Text(text, style: TextStyle(fontSize: 11, color: ok ? Colors.green.shade800 : Colors.black54)),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final cedula = _cedulaController.text;
    final esCedulaValida = esCedulaEcuatorianaValida(cedula);

    return Scaffold(
      backgroundColor: const Color(0xFFF3F6F9),
      appBar: AppBar(
        backgroundColor: const Color(0xFF0B3B60),
        elevation: 0,
        title: const Row(
          children: [
            Icon(Icons.local_hospital, color: Colors.white, size: 22),
            SizedBox(width: 8),
            Text('IESS · Turnos Móvil', style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.bold)),
          ],
        ),
        actions: [
          IconButton(
            tooltip: 'Configurar Servidor',
            icon: const Icon(Icons.settings, color: Colors.white70),
            onPressed: _showServerConfigDialog,
          ),
        ],
      ),
      body: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(20),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 420),
            child: Card(
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
              elevation: 2,
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    // Header de Bienvenida
                    const Center(
                      child: CircleAvatar(
                        radius: 30,
                        backgroundColor: Color(0xFFE8F0F8),
                        child: Icon(Icons.person_pin, size: 36, color: Color(0xFF0B3B60)),
                      ),
                    ),
                    const SizedBox(height: 12),
                    const Text(
                      'Portal Afiliados IESS',
                      textAlign: TextAlign.center,
                      style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: Color(0xFF0B3B60)),
                    ),
                    const SizedBox(height: 4),
                    const Text(
                      'Gestión móvil de citas médicas y delegación familiar',
                      textAlign: TextAlign.center,
                      style: TextStyle(fontSize: 12, color: Colors.black54),
                    ),
                    const SizedBox(height: 8),
                    Center(
                      child: InkWell(
                        onTap: _showServerConfigDialog,
                        borderRadius: BorderRadius.circular(20),
                        child: Container(
                          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                          decoration: BoxDecoration(
                            color: Colors.blue.shade50,
                            borderRadius: BorderRadius.circular(20),
                            border: Border.all(color: Colors.blue.shade200),
                          ),
                          child: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              const Icon(Icons.dns_outlined, size: 13, color: Color(0xFF0B3B60)),
                              const SizedBox(width: 4),
                              Text(
                                _api.baseUrl,
                                style: const TextStyle(fontSize: 11, color: Color(0xFF0B3B60), fontWeight: FontWeight.w600),
                              ),
                              const SizedBox(width: 4),
                              const Icon(Icons.edit, size: 11, color: Color(0xFF0B3B60)),
                            ],
                          ),
                        ),
                      ),
                    ),
                    const SizedBox(height: 16),

                    // Alertas
                    if (_errorMessage != null)
                      Container(
                        padding: const EdgeInsets.all(10),
                        margin: const EdgeInsets.only(bottom: 14),
                        decoration: BoxDecoration(
                          color: Colors.red.shade50,
                          borderRadius: BorderRadius.circular(8),
                          border: Border.all(color: Colors.red.shade200),
                        ),
                        child: Row(
                          children: [
                            const Icon(Icons.error_outline, color: Colors.red, size: 18),
                            const SizedBox(width: 8),
                            Expanded(
                              child: Text(_errorMessage!, style: const TextStyle(fontSize: 12, color: Colors.red)),
                            ),
                          ],
                        ),
                      ),

                    if (_successMessage != null)
                      Container(
                        padding: const EdgeInsets.all(10),
                        margin: const EdgeInsets.only(bottom: 14),
                        decoration: BoxDecoration(
                          color: Colors.green.shade50,
                          borderRadius: BorderRadius.circular(8),
                          border: Border.all(color: Colors.green.shade200),
                        ),
                        child: Row(
                          children: [
                            const Icon(Icons.check_circle_outline, color: Colors.green, size: 18),
                            const SizedBox(width: 8),
                            Expanded(
                              child: Text(_successMessage!, style: const TextStyle(fontSize: 12, color: Colors.green)),
                            ),
                          ],
                        ),
                      ),

                    // Formulario Paso 1 o Paso 2 (OTP)
                    if (!_isOtpStep) ...[
                      TextField(
                        controller: _cedulaController,
                        keyboardType: TextInputType.number,
                        maxLength: 10,
                        decoration: InputDecoration(
                          labelText: 'Número de Cédula Ecuatoriana',
                          hintText: '1710000000',
                          prefixIcon: const Icon(Icons.badge_outlined, size: 20),
                          border: const OutlineInputBorder(),
                          counterText: '',
                          suffixIcon: cedula.length == 10
                              ? Icon(
                                  esCedulaValida ? Icons.verified : Icons.cancel,
                                  color: esCedulaValida ? Colors.green : Colors.red,
                                )
                              : null,
                        ),
                        onChanged: (_) => setState(() {}),
                      ),
                      if (cedula.isNotEmpty && cedula.length == 10)
                        Padding(
                          padding: const EdgeInsets.only(top: 4, left: 4),
                          child: Text(
                            esCedulaValida ? '✓ Cédula ecuatoriana válida (Módulo 10)' : '✗ Cédula inválida (falla Módulo 10)',
                            style: TextStyle(
                              fontSize: 11,
                              color: esCedulaValida ? Colors.green.shade700 : Colors.red,
                              fontWeight: FontWeight.w500,
                            ),
                          ),
                        ),
                      const SizedBox(height: 14),
                      TextField(
                        controller: _passwordController,
                        obscureText: true,
                        decoration: const InputDecoration(
                          labelText: 'Contraseña',
                          prefixIcon: Icon(Icons.lock_outline, size: 20),
                          border: OutlineInputBorder(),
                        ),
                      ),
                      const SizedBox(height: 20),
                      ElevatedButton(
                        style: ElevatedButton.styleFrom(
                          backgroundColor: const Color(0xFF0B3B60),
                          padding: const EdgeInsets.symmetric(vertical: 14),
                          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                        ),
                        onPressed: (_loading || !esCedulaValida) ? null : _handleLogin,
                        child: _loading
                            ? const SizedBox(height: 18, width: 18, child: CircularProgressIndicator(color: Colors.white, strokeWidth: 2))
                            : const Text('Continuar', style: TextStyle(color: Colors.white, fontSize: 14, fontWeight: FontWeight.bold)),
                      ),
                    ] else ...[
                      if (_debugOtp.isNotEmpty)
                        Container(
                          padding: const EdgeInsets.all(10),
                          margin: const EdgeInsets.only(bottom: 14),
                          decoration: BoxDecoration(
                            color: Colors.blue.shade50,
                            borderRadius: BorderRadius.circular(8),
                            border: Border.all(color: Colors.blue.shade200),
                          ),
                          child: Row(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            children: [
                              const Text('OTP Verificación (Local):', style: TextStyle(fontSize: 12, color: Color(0xFF0B3B60))),
                              Text(_debugOtp, style: const TextStyle(fontSize: 14, fontWeight: FontWeight.bold, letterSpacing: 2)),
                            ],
                          ),
                        ),
                      TextField(
                        controller: _otpController,
                        keyboardType: TextInputType.number,
                        maxLength: 6,
                        textAlign: TextAlign.center,
                        style: const TextStyle(fontSize: 20, letterSpacing: 8, fontWeight: FontWeight.bold),
                        decoration: const InputDecoration(
                          labelText: 'Código MFA de 6 dígitos',
                          border: OutlineInputBorder(),
                          counterText: '',
                        ),
                      ),
                      const SizedBox(height: 16),
                      ElevatedButton(
                        style: ElevatedButton.styleFrom(
                          backgroundColor: const Color(0xFF0B3B60),
                          padding: const EdgeInsets.symmetric(vertical: 14),
                          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                        ),
                        onPressed: _loading ? null : _handleVerifyOtp,
                        child: _loading
                            ? const SizedBox(height: 18, width: 18, child: CircularProgressIndicator(color: Colors.white, strokeWidth: 2))
                            : const Text('Verificar e Ingresar', style: TextStyle(color: Colors.white, fontSize: 14, fontWeight: FontWeight.bold)),
                      ),
                      const SizedBox(height: 8),
                      TextButton(
                        onPressed: () => setState(() {
                          _isOtpStep = false;
                          _errorMessage = null;
                        }),
                        child: const Text('Volver a ingresar credenciales', style: TextStyle(fontSize: 12)),
                      ),
                    ],

                    const SizedBox(height: 16),
                    const Divider(),
                    const SizedBox(height: 8),

                    // Botón para Activar Cuenta Afiliado
                    OutlinedButton.icon(
                      style: OutlinedButton.styleFrom(
                        foregroundColor: const Color(0xFF0B3B60),
                        padding: const EdgeInsets.symmetric(vertical: 12),
                        side: const BorderSide(color: Color(0xFF0B3B60)),
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                      ),
                      icon: const Icon(Icons.person_add_alt, size: 18),
                      label: const Text('Activar Cuenta de Afiliado (Registro)', style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600)),
                      onPressed: () {
                        Navigator.push(
                          context,
                          MaterialPageRoute(builder: (_) => const RegistroAfiliadoScreen()),
                        );
                      },
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
