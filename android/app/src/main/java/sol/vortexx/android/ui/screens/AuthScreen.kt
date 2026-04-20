package sol.vortexx.android.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import sol.vortexx.android.auth.api.AuthRepository
import sol.vortexx.android.auth.api.AuthResult
import sol.vortexx.android.ui.theme.VortexPurple
import javax.inject.Inject

/**
 * Wave 5 auth screen — login / register toggle + submit. The VM only
 * depends on [AuthRepository]; Wave 6's seed-backed pubkey registration
 * plugs in by extending the repo impl, not this screen.
 */
@HiltViewModel
class AuthViewModel @Inject constructor(
    private val repo: AuthRepository,
) : ViewModel() {

    enum class Mode { Login, Register }

    sealed interface UiEvent {
        data object None : UiEvent
        data object Submitting : UiEvent
        data class Error(val reason: String) : UiEvent
        data object LoggedIn : UiEvent
    }

    private val _event = MutableStateFlow<UiEvent>(UiEvent.None)
    val event = _event.asStateFlow()

    fun submit(mode: Mode, username: String, password: CharArray) {
        _event.value = UiEvent.Submitting
        viewModelScope.launch {
            val res = when (mode) {
                Mode.Login    -> repo.login(username.trim(), password)
                Mode.Register -> repo.register(username.trim(), password)
            }
            _event.value = when (res) {
                is AuthResult.Ok      -> UiEvent.LoggedIn
                is AuthResult.Error   -> UiEvent.Error(res.message.ifBlank { res.code })
            }
        }
    }
}

@Composable
fun AuthScreen(
    onLoggedIn: () -> Unit,
    vm: AuthViewModel = hiltViewModel(),
) {
    val event by vm.event.collectAsState()
    var mode by remember { mutableStateOf(AuthViewModel.Mode.Login) }
    var username by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }

    if (event is AuthViewModel.UiEvent.LoggedIn) onLoggedIn()

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(MaterialTheme.colorScheme.background)
            .padding(24.dp),
        contentAlignment = Alignment.Center,
    ) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center,
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text(
                text = if (mode == AuthViewModel.Mode.Login) "Sign in" else "Create account",
                style = MaterialTheme.typography.headlineLarge,
                color = MaterialTheme.colorScheme.onBackground,
            )
            OutlinedTextField(
                value = username,
                onValueChange = { username = it },
                label = { Text("Username") },
                singleLine = true,
                modifier = Modifier.fillMaxWidth().padding(top = 24.dp),
            )
            OutlinedTextField(
                value = password,
                onValueChange = { password = it },
                label = { Text("Password") },
                singleLine = true,
                visualTransformation = PasswordVisualTransformation(),
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
                modifier = Modifier.fillMaxWidth().padding(top = 12.dp),
            )
            Button(
                onClick = { vm.submit(mode, username, password.toCharArray()) },
                enabled = username.isNotBlank() && password.isNotEmpty() &&
                    event !is AuthViewModel.UiEvent.Submitting,
                colors = ButtonDefaults.buttonColors(containerColor = VortexPurple),
                modifier = Modifier.fillMaxWidth().padding(top = 16.dp),
            ) {
                Text(
                    when (event) {
                        is AuthViewModel.UiEvent.Submitting -> "…"
                        else -> if (mode == AuthViewModel.Mode.Login) "Sign in" else "Register"
                    }
                )
            }
            TextButton(
                onClick = {
                    mode = if (mode == AuthViewModel.Mode.Login)
                        AuthViewModel.Mode.Register else AuthViewModel.Mode.Login
                },
                modifier = Modifier.padding(top = 8.dp),
            ) {
                Text(
                    if (mode == AuthViewModel.Mode.Login) "No account? Register"
                    else "Already registered? Sign in"
                )
            }
            (event as? AuthViewModel.UiEvent.Error)?.let {
                Text(
                    text = it.reason,
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.error,
                    modifier = Modifier.padding(top = 16.dp),
                )
            }
        }
    }
}
