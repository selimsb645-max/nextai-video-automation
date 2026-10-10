package com.example.nextaistudio.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
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
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.nextaistudio.data.model.ScheduleSlot
import com.example.nextaistudio.ui.theme.*
import com.example.nextaistudio.ui.viewmodel.AppScreen
import com.example.nextaistudio.ui.viewmodel.UiState

@Composable
fun DashboardScreen(
    state: UiState,
    onNavigate: (AppScreen) -> Unit,
    onStartPipelineWithFirstEligible: () -> Unit
) {
    LazyColumn(
        modifier = Modifier
            .fillMaxSize()
            .background(StudioDarkBackground)
            .padding(horizontal = 16.dp),
        contentPadding = PaddingValues(top = 16.dp, bottom = 96.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp)
    ) {
        // Studio Status Header
        item {
            Card(
                modifier = Modifier
                    .fillMaxWidth()
                    .testTag("dashboard_header_card"),
                shape = RoundedCornerShape(16.dp),
                colors = CardDefaults.cardColors(containerColor = StudioSurfaceDark),
                border = CardDefaults.outlinedCardBorder().copy(brush = androidx.compose.ui.graphics.SolidColor(BorderSubtle))
            ) {
                Column(modifier = Modifier.padding(20.dp)) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Column {
                            Text(
                                text = "NextAI Video Automation",
                                style = MaterialTheme.typography.headlineMedium,
                                color = TextPrimary,
                                fontWeight = FontWeight.Bold
                            )
                            Text(
                                text = "Private YouTube Production Factory",
                                style = MaterialTheme.typography.bodyMedium,
                                color = TextSecondary
                            )
                        }
                        Box(
                            modifier = Modifier
                                .clip(RoundedCornerShape(8.dp))
                                .background(StudioAccentGreen.copy(alpha = 0.15f))
                                .padding(horizontal = 10.dp, vertical = 6.dp)
                        ) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Box(
                                    modifier = Modifier
                                        .size(8.dp)
                                        .clip(CircleShape)
                                        .background(StudioAccentGreen)
                                )
                                Spacer(modifier = Modifier.width(6.dp))
                                Text(
                                    text = "FACTORY ONLINE",
                                    fontSize = 11.sp,
                                    fontWeight = FontWeight.Bold,
                                    color = StudioAccentGreen
                                )
                            }
                        }
                    }

                    Spacer(modifier = Modifier.height(14.dp))
                    HorizontalDivider(color = BorderSubtle)
                    Spacer(modifier = Modifier.height(14.dp))

                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Icon(
                                imageVector = Icons.Default.Schedule,
                                contentDescription = "Dhaka Time",
                                tint = StudioPrimary,
                                modifier = Modifier.size(18.dp)
                            )
                            Spacer(modifier = Modifier.width(8.dp))
                            Text(
                                text = state.currentDhakaTime.ifBlank { "Asia/Dhaka (BST, UTC+6)" },
                                style = MaterialTheme.typography.bodyLarge,
                                color = StudioPrimary,
                                fontWeight = FontWeight.SemiBold
                            )
                        }
                        Text(
                            text = "BST Clock Authoritative",
                            fontSize = 11.sp,
                            color = TextMuted
                        )
                    }
                }
            }
        }

        // Production Slots Section
        item {
            Text(
                text = "Upcoming Scheduled Slots (8–10h Lead)",
                style = MaterialTheme.typography.titleLarge,
                color = TextPrimary,
                fontWeight = FontWeight.Bold
            )
            Spacer(modifier = Modifier.height(8.dp))
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                SlotCard(
                    modifier = Modifier.weight(1f),
                    title = "Next Long Video",
                    formatLabel = "16:9 Long-Form",
                    slot = state.nextLongSlot,
                    icon = Icons.Default.VideoLibrary,
                    accentColor = StudioPrimary
                )
                SlotCard(
                    modifier = Modifier.weight(1f),
                    title = "Next Short Video",
                    formatLabel = "9:16 Vertical",
                    slot = state.nextShortSlot,
                    icon = Icons.Default.Smartphone,
                    accentColor = StudioSecondary
                )
            }
        }

        // Daily Production Targets
        item {
            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(16.dp),
                colors = CardDefaults.cardColors(containerColor = StudioSurfaceDark),
                border = CardDefaults.outlinedCardBorder().copy(brush = androidx.compose.ui.graphics.SolidColor(BorderSubtle))
            ) {
                Column(modifier = Modifier.padding(18.dp)) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Text(
                            text = "Daily Target: 2 Longs + 3 Shorts",
                            style = MaterialTheme.typography.titleMedium,
                            color = TextPrimary,
                            fontWeight = FontWeight.Bold
                        )
                        Text(
                            text = "Policy 2026-10-01",
                            fontSize = 11.sp,
                            color = StudioAccentAmber
                        )
                    }
                    Spacer(modifier = Modifier.height(12.dp))

                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(8.dp)
                    ) {
                        TargetBadge(modifier = Modifier.weight(1f), time = "19:30", kind = "Long")
                        TargetBadge(modifier = Modifier.weight(1f), time = "23:30", kind = "Long")
                        TargetBadge(modifier = Modifier.weight(1f), time = "22:00", kind = "Short")
                        TargetBadge(modifier = Modifier.weight(1f), time = "02:30", kind = "Short")
                        TargetBadge(modifier = Modifier.weight(1f), time = "06:30", kind = "Short")
                    }

                    Spacer(modifier = Modifier.height(14.dp))
                    Text(
                        text = "Zero-Cost Pipeline: Kokoro Voice (am_michael) + Pexels B-roll + FFmpeg + Resumable Upload",
                        style = MaterialTheme.typography.bodyMedium,
                        color = TextSecondary
                    )
                }
            }
        }

        // Preserved Active Uploads Notice
        item {
            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(16.dp),
                colors = CardDefaults.cardColors(containerColor = StudioSurfaceDark),
                border = CardDefaults.outlinedCardBorder().copy(brush = androidx.compose.ui.graphics.SolidColor(BorderSubtle))
            ) {
                Column(modifier = Modifier.padding(18.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(
                            imageVector = Icons.Default.Lock,
                            contentDescription = "Preserved",
                            tint = StudioAccentAmber,
                            modifier = Modifier.size(20.dp)
                        )
                        Spacer(modifier = Modifier.width(8.dp))
                        Text(
                            text = "Preserved Active Uploads (Do Not Duplicate)",
                            style = MaterialTheme.typography.titleMedium,
                            color = TextPrimary,
                            fontWeight = FontWeight.Bold
                        )
                    }
                    Spacer(modifier = Modifier.height(10.dp))
                    PreservedItem(
                        id = "OISJ6w_gFKE",
                        title = "AI Warning: 410,000 Ozempic Posts",
                        status = "Oct 1 18:30 Dhaka (Preserved Exception)"
                    )
                    Spacer(modifier = Modifier.height(6.dp))
                    PreservedItem(
                        id = "o4LMHDzIWec",
                        title = "Gemini 4 Argon: 1M Token Catch",
                        status = "Oct 1 22:00 Dhaka Short (Uploaded Private)"
                    )
                    Spacer(modifier = Modifier.height(6.dp))
                    PreservedItem(
                        id = "vLbiHvf4XYo",
                        title = "OpenAI Dots: What Agents Can Do",
                        status = "Oct 1 23:30 Dhaka Long (Uploaded Private)"
                    )
                }
            }
        }

        // Quick Action Buttons
        item {
            Text(
                text = "Quick Controls",
                style = MaterialTheme.typography.titleLarge,
                color = TextPrimary,
                fontWeight = FontWeight.Bold
            )
            Spacer(modifier = Modifier.height(8.dp))
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                Button(
                    onClick = onStartPipelineWithFirstEligible,
                    modifier = Modifier
                        .weight(1f)
                        .height(50.dp)
                        .testTag("dashboard_produce_button"),
                    shape = RoundedCornerShape(12.dp),
                    colors = ButtonDefaults.buttonColors(containerColor = StudioPrimary)
                ) {
                    Icon(imageVector = Icons.Default.PlayArrow, contentDescription = null)
                    Spacer(modifier = Modifier.width(6.dp))
                    Text("Produce Next", fontWeight = FontWeight.Bold, color = Color.Black)
                }

                OutlinedButton(
                    onClick = { onNavigate(AppScreen.LIBRARY) },
                    modifier = Modifier
                        .weight(1f)
                        .height(50.dp)
                        .testTag("dashboard_library_button"),
                    shape = RoundedCornerShape(12.dp),
                    border = ButtonDefaults.outlinedButtonBorder.copy(brush = androidx.compose.ui.graphics.SolidColor(StudioPrimary))
                ) {
                    Icon(imageVector = Icons.Default.List, contentDescription = null, tint = StudioPrimary)
                    Spacer(modifier = Modifier.width(6.dp))
                    Text("Browse Library", color = StudioPrimary)
                }
            }
        }

        // Production Statistics Grid
        item {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                StatCard(
                    modifier = Modifier.weight(1f),
                    title = "Published Total",
                    value = "${state.publishedLog.size}",
                    subtitle = "Archive entries",
                    color = StudioPrimary
                )
                StatCard(
                    modifier = Modifier.weight(1f),
                    title = "Active Runs",
                    value = "${state.activeRuns.size}",
                    subtitle = "In queue / scheduled",
                    color = StudioAccentGreen
                )
                StatCard(
                    modifier = Modifier.weight(1f),
                    title = "Workflows",
                    value = "${state.workflowTemplates.size}",
                    subtitle = "${state.workflowTemplates.count { it.isActive }} active",
                    color = StudioSecondary
                )
            }
        }
    }
}

@Composable
private fun SlotCard(
    modifier: Modifier = Modifier,
    title: String,
    formatLabel: String,
    slot: ScheduleSlot?,
    icon: ImageVector,
    accentColor: Color
) {
    Card(
        modifier = modifier,
        shape = RoundedCornerShape(14.dp),
        colors = CardDefaults.cardColors(containerColor = StudioSurfaceDark),
        border = CardDefaults.outlinedCardBorder().copy(brush = androidx.compose.ui.graphics.SolidColor(BorderSubtle))
    ) {
        Column(modifier = Modifier.padding(14.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(imageVector = icon, contentDescription = null, tint = accentColor, modifier = Modifier.size(18.dp))
                Spacer(modifier = Modifier.width(6.dp))
                Text(text = title, fontSize = 13.sp, color = TextSecondary, fontWeight = FontWeight.Medium)
            }
            Spacer(modifier = Modifier.height(8.dp))
            Text(
                text = slot?.timeLabel ?: "--:-- BST",
                fontSize = 20.sp,
                fontWeight = FontWeight.Bold,
                color = TextPrimary
            )
            Text(
                text = slot?.dateString ?: "Checking slot...",
                fontSize = 11.sp,
                color = TextMuted
            )
            Spacer(modifier = Modifier.height(6.dp))
            Box(
                modifier = Modifier
                    .clip(RoundedCornerShape(6.dp))
                    .background(if (slot?.isEligible == true) StudioAccentGreen.copy(alpha = 0.15f) else StudioAccentAmber.copy(alpha = 0.15f))
                    .padding(horizontal = 8.dp, vertical = 4.dp)
            ) {
                Text(
                    text = slot?.statusText ?: "Lead calculation...",
                    fontSize = 10.sp,
                    color = if (slot?.isEligible == true) StudioAccentGreen else StudioAccentAmber,
                    fontWeight = FontWeight.SemiBold
                )
            }
        }
    }
}

@Composable
private fun TargetBadge(modifier: Modifier = Modifier, time: String, kind: String) {
    Box(
        modifier = modifier
            .clip(RoundedCornerShape(8.dp))
            .background(StudioSurfaceCard)
            .padding(vertical = 8.dp),
        contentAlignment = Alignment.Center
    ) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Text(text = time, fontSize = 13.sp, fontWeight = FontWeight.Bold, color = TextPrimary)
            Text(text = kind, fontSize = 10.sp, color = TextSecondary)
        }
    }
}

@Composable
private fun PreservedItem(id: String, title: String, status: String) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clip(RoundedCornerShape(8.dp))
            .background(StudioSurfaceCard)
            .padding(10.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Box(
            modifier = Modifier
                .clip(RoundedCornerShape(4.dp))
                .background(BorderSubtle)
                .padding(horizontal = 6.dp, vertical = 2.dp)
        ) {
            Text(text = id, fontSize = 10.sp, color = StudioPrimary, fontWeight = FontWeight.Bold)
        }
        Spacer(modifier = Modifier.width(10.dp))
        Column(modifier = Modifier.weight(1f)) {
            Text(text = title, fontSize = 12.sp, color = TextPrimary, fontWeight = FontWeight.Medium)
            Text(text = status, fontSize = 10.sp, color = TextMuted)
        }
    }
}

@Composable
private fun StatCard(modifier: Modifier = Modifier, title: String, value: String, subtitle: String, color: Color) {
    Card(
        modifier = modifier,
        shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.cardColors(containerColor = StudioSurfaceDark),
        border = CardDefaults.outlinedCardBorder().copy(brush = androidx.compose.ui.graphics.SolidColor(BorderSubtle))
    ) {
        Column(modifier = Modifier.padding(12.dp)) {
            Text(text = title, fontSize = 11.sp, color = TextSecondary)
            Spacer(modifier = Modifier.height(4.dp))
            Text(text = value, fontSize = 22.sp, fontWeight = FontWeight.Bold, color = color)
            Text(text = subtitle, fontSize = 10.sp, color = TextMuted)
        }
    }
}
