import 'package:flutter/material.dart';
import '../services/api_service.dart';
import '../services/security_utils.dart';

class RegistroAfiliadoScreen extends StatefulWidget {
  const RegistroAfiliadoScreen({super.key});

  @override
  State<RegistroAfiliadoScreen> createState() => _RegistroAfiliadoScreenState();
}

class _RegistroAfiliadoScreenState extends State<RegistroAfiliadoScreen> {
  final _api = ApiService();

  int _currentStep = 0; // 0: Cédula, 1: Datos & Clave, 2: OTP
  bool _loading = false;
  String? _errorMessage;

  // Paso 0: Cédula
  final _cedulaController = TextEditingController();
  Map<String, dynamic>? _padronData;

  // Paso 1: Datos contacto y contraseña
  final _emailController = TextEditingController();
  final _telefonoController = TextEditingController();
  final _passwordController = TextEditingController();

  // Paso 2: OTP
  final _otpController = TextEditingController();
  String _debugOtp = '';

  @override
  void dispose() {
    _cedulaController.dispose();
    _emailController.dispose();
    _telefonoController.dispose();
    _passwordController.dispose();
    _otpController.dispose();
    super.dispose();
  }

  Future<void> _handleConsultarPadron() async {
    final cedula = _cedulaController.text.trim();
    if (!esCedulaEcuatorianaValida(cedula)) {
      setState(() => _errorMessage = 'Ingrese un número de cédula válido según el algoritmo Módulo 10 del Registro Civil.');
      return;
    }

    setState(() {
      _loading = true;
      _errorMessage = null;
    });

    try {
      final data = await _api.consultarPadron(cedula);
      setState(() {
        _padronData = data;
        _currentStep = 1;
      });
    } on ApiException catch (e) {
      setState(() => _errorMessage = e.message);
    } catch (e) {
      setState(() => _errorMessage = 'Error de conexión: $e');
    } finally {
      setState(() => _loading = false);
    }
  }

  Future<void> _handleSolicitarOtp() async {
    final cedula = _cedulaController.text.trim();
    final email = _emailController.text.trim();
    final telefono = _telefonoController.text.trim();
    final password = _passwordController.text;

    final val = validarPoliticaClave(
      password,
      cedula,
      _padronData?['fecha_nacimiento']?.toString(),
    );

    if (!val.esValida) {
      setState(() => _errorMessage = 'La contraseña no cumple con los requisitos de seguridad.');
      return;
    }

    if (email.isEmpty || !email.contains('@')) {
      setState(() => _errorMessage = 'Ingrese un correo electrónico válido.');
      return;
    }

    if (telefono.length < 9) {
      setState(() => _errorMessage = 'Ingrese un número de teléfono celular válido.');
      return;
    }

    setState(() {
      _loading = true;
      _errorMessage = null;
    });

    try {
      final res = await _api.solicitarOtpRegistro(
        cedula: cedula,
        email: email,
        telefono: telefono,
        password: password,
      );
      setState(() {
        _debugOtp = res['debug_otp']?.toString() ?? '';
        _otpController.text = _debugOtp;
        _currentStep = 2;
      });
    } on ApiException catch (e) {
      setState(() => _errorMessage = e.message);
    } catch (e) {
      setState(() => _errorMessage = 'Error al solicitar código OTP: $e');
    } finally {
      setState(() => _loading = false);
    }
  }

  Future<void> _handleConfirmarOtp() async {
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
      final res = await _api.confirmarOtpRegistro(cedula: cedula, otp: otp);
      if (!mounted) return;

      showDialog(
        context: context,
        barrierDismissible: false,
        builder: (ctx) => AlertDialog(
          title: const Row(
            children: [
              Icon(Icons.verified, color: Colors.green),
              SizedBox(width: 8),
              Text('Cuenta Activada', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
            ],
          ),
          content: Text(
            res['mensaje']?.toString() ?? 'Su cuenta de afiliado ha sido verificada y activada exitosamente. Ya puede iniciar sesión.',
            style: const TextStyle(fontSize: 13),
          ),
          actions: [
            ElevatedButton(
              style: ElevatedButton.styleFrom(backgroundColor: const Color(0xFF0B3B60)),
              onPressed: () {
                Navigator.pop(ctx);
                Navigator.pop(context); // Volver al Login
              },
              child: const Text('Iniciar Sesión', style: TextStyle(color: Colors.white)),
            ),
          ],
        ),
      );
    } on ApiException catch (e) {
      setState(() => _errorMessage = e.message);
    } catch (e) {
      setState(() => _errorMessage = 'Error al verificar OTP: $e');
    } finally {
      setState(() => _loading = false);
    }
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
        title: const Text('Activar Cuenta de Afiliado', style: TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.bold)),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back, color: Colors.white),
          onPressed: () => Navigator.pop(context),
        ),
      ),
      body: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(20),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 440),
            child: Card(
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
              elevation: 2,
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    // Stepper visual
                    Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        _buildStepIndicator(0, 'Identidad'),
                        _buildStepDivider(),
                        _buildStepIndicator(1, 'Contacto'),
                        _buildStepDivider(),
                        _buildStepIndicator(2, 'Verificación'),
                      ],
                    ),
                    const SizedBox(height: 20),

                    // Error alert
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
                            Expanded(child: Text(_errorMessage!, style: const TextStyle(fontSize: 12, color: Colors.red))),
                          ],
                        ),
                      ),

                    // PASO 0: CÉDULA
                    if (_currentStep == 0) ...[
                      const Text(
                        'Paso 1: Validación Institucional',
                        style: TextStyle(fontSize: 15, fontWeight: FontWeight.bold, color: Color(0xFF0B3B60)),
                      ),
                      const SizedBox(height: 6),
                      const Text(
                        'Ingrese su cédula ecuatoriana para contrastar su identidad contra el padrón del IESS (Req. 102).',
                        style: TextStyle(fontSize: 12, color: Colors.black54),
                      ),
                      const SizedBox(height: 16),
                      TextField(
                        controller: _cedulaController,
                        keyboardType: TextInputType.number,
                        maxLength: 10,
                        decoration: InputDecoration(
                          labelText: 'Cédula Ecuatoriana',
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
                      if (cedula.length == 10)
                        Padding(
                          padding: const EdgeInsets.only(top: 4, left: 4),
                          child: Text(
                            esCedulaValida ? '✓ Cédula válida (Módulo 10)' : '✗ Cédula no cumple Módulo 10',
                            style: TextStyle(
                              fontSize: 11,
                              color: esCedulaValida ? Colors.green.shade700 : Colors.red,
                              fontWeight: FontWeight.w500,
                            ),
                          ),
                        ),
                      const SizedBox(height: 20),
                      ElevatedButton(
                        style: ElevatedButton.styleFrom(
                          backgroundColor: const Color(0xFF0B3B60),
                          padding: const EdgeInsets.symmetric(vertical: 14),
                          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                        ),
                        onPressed: (_loading || !esCedulaValida) ? null : _handleConsultarPadron,
                        child: _loading
                            ? const SizedBox(height: 18, width: 18, child: CircularProgressIndicator(color: Colors.white, strokeWidth: 2))
                            : const Text('Validar Identidad en IESS', style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
                      ),
                    ],

                    // PASO 1: DATOS Y CONTRASEÑA
                    if (_currentStep == 1 && _padronData != null) ...[
                      Container(
                        padding: const EdgeInsets.all(12),
                        decoration: BoxDecoration(
                          color: Colors.blue.shade50,
                          borderRadius: BorderRadius.circular(8),
                          border: Border.all(color: Colors.blue.shade200),
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Text('Identidad verificada en Padrón IESS:', style: TextStyle(fontSize: 11, color: Color(0xFF0B3B60))),
                            const SizedBox(height: 2),
                            Text(
                              _padronData!['nombres']?.toString() ?? '',
                              style: const TextStyle(fontSize: 13, fontWeight: FontWeight.bold, color: Color(0xFF0B3B60)),
                            ),
                            Text(
                              'Cédula: ${_padronData!['cedula']}  ·  Nacimiento: ${_padronData!['fecha_nacimiento']}',
                              style: const TextStyle(fontSize: 11, color: Colors.black87),
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(height: 14),
                      const Text(
                        'Minimización de Datos (Req. 102): Solo se requiere registrar su correo electrónico y teléfono celular para verificación OTP.',
                        style: TextStyle(fontSize: 11, color: Colors.black54),
                      ),
                      const SizedBox(height: 12),
                      TextField(
                        controller: _emailController,
                        keyboardType: TextInputType.emailAddress,
                        decoration: const InputDecoration(
                          labelText: 'Correo Electrónico Personal',
                          prefixIcon: Icon(Icons.email_outlined, size: 20),
                          border: OutlineInputBorder(),
                        ),
                      ),
                      const SizedBox(height: 10),
                      TextField(
                        controller: _telefonoController,
                        keyboardType: TextInputType.phone,
                        maxLength: 10,
                        decoration: const InputDecoration(
                          labelText: 'Teléfono Móvil (Celular)',
                          prefixIcon: Icon(Icons.phone_android_outlined, size: 20),
                          border: OutlineInputBorder(),
                          counterText: '',
                        ),
                      ),
                      const SizedBox(height: 10),
                      TextField(
                        controller: _passwordController,
                        obscureText: true,
                        decoration: const InputDecoration(
                          labelText: 'Crear Contraseña Robusta',
                          prefixIcon: Icon(Icons.lock_outline, size: 20),
                          border: OutlineInputBorder(),
                        ),
                        onChanged: (_) => setState(() {}),
                      ),
                      const SizedBox(height: 8),

                      // Indicadores de clave robusta (Req. 107)
                      Builder(
                        builder: (_) {
                          final val = validarPoliticaClave(
                            _passwordController.text,
                            _cedulaController.text,
                            _padronData?['fecha_nacimiento']?.toString(),
                          );
                          return Container(
                            padding: const EdgeInsets.all(8),
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
                              ],
                            ),
                          );
                        },
                      ),
                      const SizedBox(height: 16),
                      ElevatedButton(
                        style: ElevatedButton.styleFrom(
                          backgroundColor: const Color(0xFF0B3B60),
                          padding: const EdgeInsets.symmetric(vertical: 14),
                          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                        ),
                        onPressed: _loading ? null : _handleSolicitarOtp,
                        child: _loading
                            ? const SizedBox(height: 18, width: 18, child: CircularProgressIndicator(color: Colors.white, strokeWidth: 2))
                            : const Text('Enviar Código OTP de Verificación', style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
                      ),
                    ],

                    // PASO 2: OTP
                    if (_currentStep == 2) ...[
                      const Text(
                        'Paso 3: Verificación de Contacto (OTP)',
                        style: TextStyle(fontSize: 15, fontWeight: FontWeight.bold, color: Color(0xFF0B3B60)),
                      ),
                      const SizedBox(height: 6),
                      Text(
                        'Ingrese el código temporal de 6 dígitos enviado a ${_emailController.text} y ${_telefonoController.text}:',
                        style: const TextStyle(fontSize: 12, color: Colors.black54),
                      ),
                      const SizedBox(height: 14),
                      if (_debugOtp.isNotEmpty)
                        Container(
                          padding: const EdgeInsets.all(10),
                          margin: const EdgeInsets.only(bottom: 12),
                          decoration: BoxDecoration(
                            color: Colors.blue.shade50,
                            borderRadius: BorderRadius.circular(8),
                            border: Border.all(color: Colors.blue.shade200),
                          ),
                          child: Row(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            children: [
                              const Text('OTP Verificación (Local):', style: TextStyle(fontSize: 12, color: Color(0xFF0B3B60))),
                              Text(_debugOtp, style: const TextStyle(fontSize: 15, fontWeight: FontWeight.bold, letterSpacing: 2)),
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
                          labelText: 'Código OTP de 6 dígitos',
                          border: OutlineInputBorder(),
                          counterText: '',
                        ),
                      ),
                      const SizedBox(height: 16),
                      ElevatedButton(
                        style: ElevatedButton.styleFrom(
                          backgroundColor: Colors.green.shade800,
                          padding: const EdgeInsets.symmetric(vertical: 14),
                          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                        ),
                        onPressed: _loading ? null : _handleConfirmarOtp,
                        child: _loading
                            ? const SizedBox(height: 18, width: 18, child: CircularProgressIndicator(color: Colors.white, strokeWidth: 2))
                            : const Text('Confirmar y Activar Cuenta', style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
                      ),
                    ],
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildStepIndicator(int stepIndex, String title) {
    final isDone = _currentStep > stepIndex;
    final isCurrent = _currentStep == stepIndex;

    return Column(
      children: [
        CircleAvatar(
          radius: 14,
          backgroundColor: isDone
              ? Colors.green
              : (isCurrent ? const Color(0xFF0B3B60) : Colors.grey.shade300),
          child: isDone
              ? const Icon(Icons.check, size: 14, color: Colors.white)
              : Text(
                  '${stepIndex + 1}',
                  style: TextStyle(
                    fontSize: 11,
                    color: isCurrent ? Colors.white : Colors.black54,
                    fontWeight: FontWeight.bold,
                  ),
                ),
        ),
        const SizedBox(height: 4),
        Text(
          title,
          style: TextStyle(
            fontSize: 10,
            fontWeight: isCurrent ? FontWeight.bold : FontWeight.normal,
            color: isCurrent ? const Color(0xFF0B3B60) : Colors.black54,
          ),
        ),
      ],
    );
  }

  Widget _buildStepDivider() {
    return Container(
      width: 32,
      height: 2,
      margin: const EdgeInsets.only(bottom: 16, left: 4, right: 4),
      color: Colors.grey.shade300,
    );
  }
}

