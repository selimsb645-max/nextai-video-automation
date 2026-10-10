package com.example.nextaistudio.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.nextaistudio.data.model.CheckStatus
import com.example.nextaistudio.data.model.PreflightCheck
import com.example.nextaistudio.ui.theme.*
import com.example.nextaistudio.ui.viewmodel.UiState

@Composable
fun PreflightScreen(
    state: UiState,
    onRunDiagnostics: () -> Unit
) {
    LazyColumn(
        modifier = Modifier
            .fillMaxSize()
            .background(StudioDarkBackground)
            .padding(horizontal = 16.dp),
        contentPadding = PaddingValues(top = 16.dp, bottom = 96.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp)
    ) {
        item {
            Column {
                Text(
                    text = "System Preflight & Diagnostics",
                    style = MaterialTheme.typography.headlineMedium,
                    color = TextPrimary,
                    fontWeight = FontWeight.Bold
                )
                Text(
                    text = "Offline-only safety verification (based on tools/preflight.py)",
                    style = MaterialTheme.typography.bodyMedium,
                    color = TextSecondary
                )
                Spacer(modifier = Modifier.height(14.dp))

                Button(
                    onClick = onRunDiagnostics,
                    enabled = !state.isRunningPreflight,
                    modifier = Modifier
                        .fillMaxWidth()
                        .height(48.dp)
                        .testTag("run_diagnostics_button"),
                    shape = RoundedCornerShape(10.dp),
                    colors = ButtonDefaults.buttonColors(containerColor = StudioPrimary)
                ) {
                    if (state.isRunningPreflight) {
                        CircularProgressIndicator(modifier = Modifier.size(18.dp), color = Color.Black)
                        Spacer(modifier = Modifier.width(8.dp))
                        Text("Verifying System Integrity...", color = Color.Black)
                    } else {
                        Icon(Icons.Default.Speed, contentDescription = null, tint = Color.Black)
                        Spacer(modifier = Modifier.width(8.dp))
                        Text("Run Complete Diagnostic Suite", color = Color.Black, fontWeight = FontWeight.Bold)
                    }
                }
            }
        }

        if (state.preflightChecks.isEmpty() && !state.isRunningPreflight) {
            item {
                Card(
                    modifier = Modifier.fillMaxWidth(),
                    shape = RoundedCornerShape(14.dp),
                    colors = CardDefaults.cardColors(containerColor = StudioSurfaceDark),
                    border = CardDefaults.outlinedCardBorder().copy(brush = androidx.compose.ui.graphics.SolidColor(BorderSubtle))
                ) {
                    Column(
                        modifier = Modifier.padding(24.dp),
                        horizontalAlignment = Alignment.CenterHorizontally
                    ) {
                        Icon(Icons.Default.VerifiedUser, contentDescription = null, tint = StudioPrimary, modifier = Modifier.size(48.dp))
                        Spacer(modifier = Modifier.height(12.dp))
                        Text(
                            text = "Preflight Diagnostics Ready",
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.Bold,
                            color = TextPrimary
                        )
                        Spacer(modifier = Modifier.height(6.dp))
                        Text(
                            text = "Click 'Run Complete Diagnostic Suite' above to test slot algorithms, audio gates, content eligibility, and integrity rules.",
                            fontSize = 12.sp,
                            color = TextSecondary,
                            textAlign = androidx.compose.ui.text.style.TextAlign.Center
                        )
                    }
                }
            }
        }

        items(state.preflightChecks, key = { it.id }) { check ->
            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(14.dp),
                colors = CardDefaults.cardColors(containerColor = StudioSurfaceDark),
                border = CardDefaults.outlinedCardBorder().copy(brush = androidx.compose.ui.graphics.SolidColor(BorderSubtle))
            ) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(16.dp),
                    verticalAlignment = Alignment.Top
                ) {
                    Box(
                        modifier = Modifier
                            .size(28.dp)
                            .clip(CircleShape)
                            .background(
                                when (check.status) {
                                    CheckStatus.PASSED -> StudioAccentGreen.copy(alpha = 0.2f)
                                    CheckStatus.WARNING -> StudioAccentAmber.copy(alpha = 0.2f)
                                    CheckStatus.FAILED -> StudioAccentRed.copy(alpha = 0.2f)
                                }
                            ),
                        contentAlignment = Alignment.Center
                    ) {
                        Icon(
                            imageVector = when (check.status) {
                                CheckStatus.PASSED -> Icons.Default.Check
                                CheckStatus.WARNING -> Icons.Default.Warning
                                CheckStatus.FAILED -> Icons.Default.Close
                            },
                            contentDescription = null,
                            tint = when (check.status) {
                                CheckStatus.PASSED -> StudioAccentGreen
                                CheckStatus.WARNING -> StudioAccentAmber
                                CheckStatus.FAILED -> StudioAccentRed
                            },
                            modifier = Modifier.size(16.dp)
                        )
                    }

                    Spacer(modifier = Modifier.width(12.dp))

                    Column(modifier = Modifier.weight(1f)) {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Text(
                                text = check.name,
                                style = MaterialTheme.typography.titleMedium,
                                fontWeight = FontWeight.Bold,
                                color = TextPrimary
                            )
                            Box(
                                modifier = Modifier
                                    .clip(RoundedCornerShape(4.dp))
                                    .background(BorderSubtle)
                                    .padding(horizontal = 6.dp, vertical = 2.dp)
                            ) {
                                Text(text = check.category, fontSize = 9.sp, color = TextMuted)
                            }
                        }

                        Spacer(modifier = Modifier.height(4.dp))
                        Text(text = check.message, fontSize = 12.sp, color = StudioPrimary)

                        Spacer(modifier = Modifier.height(4.dp))
                        Text(text = check.detail, fontSize = 11.sp, color = TextSecondary)
                    }
                }
            }
        }
    }
}
