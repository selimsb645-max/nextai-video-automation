package com.example.nextaistudio.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable

private val DarkColorScheme = darkColorScheme(
    primary = StudioPrimary,
    onPrimary = StudioOnPrimary,
    primaryContainer = StudioPrimaryContainer,
    secondary = StudioSecondary,
    secondaryContainer = StudioSecondaryContainer,
    background = StudioDarkBackground,
    surface = StudioSurfaceDark,
    surfaceVariant = StudioSurfaceCard,
    error = StudioAccentRed
)

@Composable
fun NextAIStudioTheme(
    darkTheme: Boolean = true, // Defaults to sleek dark studio theme
    content: @Composable () -> Unit
) {
    MaterialTheme(
        colorScheme = DarkColorScheme,
        typography = Typography,
        content = content
    )
}
