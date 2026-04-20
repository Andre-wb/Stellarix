package sol.vortexx.android.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.input.TextFieldValue
import androidx.compose.ui.text.input.TransformedText
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/**
 * Minimal Gravitix IDE view. Single-buffer text editor with keyword
 * highlighting built via an in-place [VisualTransformation] — no parser,
 * no AST, just a regex over known keywords. Enough to read and tweak
 * example snippets from the docs; a proper editor (tree-sitter, LSP,
 * undo stack) lives in a later milestone.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun IdeScreen(onBack: () -> Unit) {
    var field by remember {
        mutableStateOf(TextFieldValue(SAMPLE_CODE))
    }

    Scaffold(
        containerColor = Color(0xFF0A0A14),
        topBar = {
            TopAppBar(
                title = { Text("Gravitix IDE") },
                navigationIcon = {
                    IconButton(onClick = onBack) { Icon(Icons.Filled.ArrowBack, contentDescription = "Back") }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = Color(0xFF0A0A14),
                ),
            )
        },
    ) { padding ->
        Column(
            Modifier
                .padding(padding)
                .fillMaxSize()
                .background(Color(0xFF0A0A14))
                .verticalScroll(rememberScrollState())
                .padding(12.dp),
        ) {
            BasicTextField(
                value = field,
                onValueChange = { field = it },
                textStyle = TextStyle(
                    color = Color(0xFFEEEEF2),
                    fontSize = 13.sp,
                    fontFamily = FontFamily.Monospace,
                ),
                visualTransformation = SyntaxHighlight(),
                modifier = Modifier.fillMaxWidth(),
                cursorBrush = androidx.compose.ui.graphics.SolidColor(
                    MaterialTheme.colorScheme.primary,
                ),
            )
        }
    }
}

/**
 * VisualTransformation that recolours Gravitix keywords + string literals.
 * Identity offset mapping — no char count changes — so cursor positions
 * line up trivially.
 */
private class SyntaxHighlight : VisualTransformation {
    override fun filter(text: AnnotatedString): TransformedText {
        val annotated = buildAnnotatedString {
            append(text.text)
            KEYWORDS.findAll(text.text).forEach { m ->
                addStyle(SpanStyle(color = Color(0xFFA855F7)), m.range.first, m.range.last + 1)
            }
            STRINGS.findAll(text.text).forEach { m ->
                addStyle(SpanStyle(color = Color(0xFF86EFAC)), m.range.first, m.range.last + 1)
            }
            COMMENTS.findAll(text.text).forEach { m ->
                addStyle(SpanStyle(color = Color(0xFF6B7280)), m.range.first, m.range.last + 1)
            }
        }
        return TransformedText(annotated, OffsetIdentity)
    }

    private companion object {
        val KEYWORDS = Regex("\\b(state|flow|guard|match|wait|break|continue|elif|struct|enum|impl|self|every|pipe|ctx|let|fn|msg|void|null|try|catch|finally|throw|return|emit|emit_to|handler|int|float|str|bool)\\b")
        val STRINGS  = Regex("\"[^\"\\n]*\"")
        val COMMENTS = Regex("//[^\\n]*")
    }
}

private object OffsetIdentity : androidx.compose.ui.text.input.OffsetMapping {
    override fun originalToTransformed(offset: Int) = offset
    override fun transformedToOriginal(offset: Int) = offset
}

private const val SAMPLE_CODE = """
// Gravitix sample — counter bot
state counter: int = 0

handler /start {
    emit "Hello from Vortex!"
}

handler /inc {
    counter = counter + 1
    emit "count = " + counter
}
"""
