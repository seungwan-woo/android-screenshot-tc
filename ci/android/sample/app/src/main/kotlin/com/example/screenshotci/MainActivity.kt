package com.example.screenshotci

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.background
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.consumeWindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.ExperimentalComposeUiApi
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.testTagsAsResourceId
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp

private val LightColors = lightColorScheme(
    background = Color(0xFFF4F6FC), onBackground = Color(0xFF171A24),
    surface = Color(0xFFFFFFFF), onSurface = Color(0xFF171A24),
    onSurfaceVariant = Color(0xFF46516D), outlineVariant = Color(0xFFDCE2EF),
    primary = Color(0xFF2254CA), onPrimary = Color.White,
    primaryContainer = Color(0xFFE5EDFF), onPrimaryContainer = Color(0xFF153B8F),
)

private val DarkColors = darkColorScheme(
    background = Color(0xFF111318), onBackground = Color(0xFFF2F4FA),
    surface = Color(0xFF1D2029), onSurface = Color(0xFFF2F4FA),
    onSurfaceVariant = Color(0xFFB8C1D7), outlineVariant = Color(0xFF393E4D),
    primary = Color(0xFFAEC6FF), onPrimary = Color(0xFF102D68),
    primaryContainer = Color(0xFF263E73), onPrimaryContainer = Color(0xFFDCE7FF),
)

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            val dark = isSystemInDarkTheme()
            MaterialTheme(colorScheme = if (dark) DarkColors else LightColors) {
                ScreenshotLab(dark)
            }
        }
    }
}

@OptIn(ExperimentalComposeUiApi::class)
@Composable
private fun ScreenshotLab(dark: Boolean) {
    var updated by rememberSaveable { mutableStateOf(false) }
    val colors = MaterialTheme.colorScheme
    Scaffold(
        modifier = Modifier.fillMaxSize().semantics { testTagsAsResourceId = true },
        containerColor = colors.background,
        contentWindowInsets = WindowInsets.safeDrawing,
    ) { safePadding ->
        Column(
            modifier = Modifier.fillMaxSize()
                .padding(safePadding)
                .consumeWindowInsets(safePadding)
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 24.dp, vertical = 28.dp),
            verticalArrangement = Arrangement.spacedBy(24.dp),
        ) {
            Column(verticalArrangement = Arrangement.spacedBy(5.dp)) {
                Text("Screenshot Lab", style = MaterialTheme.typography.displaySmall, fontWeight = FontWeight.Bold)
                Text("Android emulator", color = colors.onSurfaceVariant, style = MaterialTheme.typography.bodyLarge)
            }
            Surface(shape = RoundedCornerShape(28.dp), color = colors.surface) {
                Column(Modifier.fillMaxWidth().padding(22.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
                    Text("Capture state", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                    Surface(
                        shape = RoundedCornerShape(16.dp),
                        color = colors.primaryContainer,
                        contentColor = colors.onPrimaryContainer,
                    ) {
                        Row(
                            modifier = Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 12.dp),
                            horizontalArrangement = Arrangement.spacedBy(10.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Box(Modifier.size(8.dp).background(colors.onPrimaryContainer, CircleShape))
                            Text(
                                if (updated) "State: UPDATED" else "State: READY",
                                style = MaterialTheme.typography.labelLarge,
                                fontWeight = FontWeight.Bold,
                            )
                        }
                    }
                    HorizontalDivider(color = colors.outlineVariant)
                    Text(if (dark) "Theme: Dark" else "Theme: Light", color = colors.onSurfaceVariant)
                    Button(
                        onClick = { updated = !updated },
                        modifier = Modifier.fillMaxWidth().heightIn(min = 56.dp).testTag("update_state"),
                        shape = RoundedCornerShape(28.dp),
                    ) { Text("Update state", style = MaterialTheme.typography.titleMedium) }
                }
            }
        }
    }
}
