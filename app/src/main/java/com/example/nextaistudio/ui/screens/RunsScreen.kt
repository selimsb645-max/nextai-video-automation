package com.example.nextaistudio.ui.screens

import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
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
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import com.example.nextaistudio.data.model.RunResult
import com.example.nextaistudio.ui.theme.*
import com.example.nextaistudio.ui.viewmodel.UiState

@Composable
fun RunsScreen(
    state: UiState,
    onSelectRun: (RunResult?) -> Unit
) {
    val context = LocalContext.current

    Box(modifier = Modifier.fillMaxSize().background(StudioDarkBackground)) {
        LazyColumn(
            modifier = Modifier
                .fillMaxSize()
                .padding(horizontal = 16.dp),
            contentPadding = PaddingValues(top = 16.dp, bottom = 96.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp)
        ) {
            // Header
            item {
                Column {
                    Text(
                        text = "Production Runs & Log",
                        style = MaterialTheme.typography.headlineMedium,
                        color = TextPrimary,
                        fontWeight = FontWeight.Bold
                    )
                    Text(
                        text = "Real-time queue tracking & published video registry",
                        style = MaterialTheme.typography.bodyMedium,
                        color = TextSecondary
                    )
                }
            }

            // Active Runs Section
            item {
                Text(
                    text = "Active Runs (${state.activeRuns.size})",
                    style = MaterialTheme.typography.titleMedium,
                    color = TextPrimary,
                    fontWeight = FontWeight.Bold
                )
            }

            items(state.activeRuns, key = { it.id }) { run ->
                Card(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clickable { onSelectRun(run) }
                        .testTag("run_card_${run.id}"),
                    shape = RoundedCornerShape(14.dp),
                    colors = CardDefaults.cardColors(containerColor = StudioSurfaceDark),
                    border = CardDefaults.outlinedCardBorder().copy(brush = androidx.compose.ui.graphics.SolidColor(BorderSubtle))
                ) {
                    Column(modifier = Modifier.padding(16.dp)) {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Box(
                                modifier = Modifier
                                    .clip(RoundedCornerShape(6.dp))
                                    .background(StudioAccentAmber.copy(alpha = 0.15f))
                                    .padding(horizontal = 8.dp, vertical = 3.dp)
                            ) {
                                Text(
                                    text = run.status.uppercase(),
                                    fontSize = 10.sp,
                                    fontWeight = FontWeight.Bold,
                                    color = StudioAccentAmber
                                )
                            }
                            Text(text = run.date, fontSize = 11.sp, color = TextMuted)
                        }

                        Spacer(modifier = Modifier.height(8.dp))
                        Text(
                            text = run.id,
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.Bold,
                            color = TextPrimary
                        )

                        Spacer(modifier = Modifier.height(4.dp))
                        Text(
                            text = "Video ID: ${run.videoId} • Scheduled: ${run.scheduledFor}",
                            fontSize = 11.sp,
                            color = StudioPrimary
                        )

                        Spacer(modifier = Modifier.height(8.dp))
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Icon(
                                imageVector = Icons.Default.Info,
                                contentDescription = null,
                                tint = StudioAccentAmber,
                                modifier = Modifier.size(14.dp)
                            )
                            Spacer(modifier = Modifier.width(6.dp))
                            Text(
                                text = "Thumbnail: ${run.thumbnailStatus.replace("_", " ")}",
                                fontSize = 11.sp,
                                color = TextSecondary
                            )
                        }

                        Spacer(modifier = Modifier.height(10.dp))
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.End
                        ) {
                            Button(
                                onClick = {
                                    val intent = Intent(Intent.ACTION_VIEW, Uri.parse(run.url))
                                    context.startActivity(intent)
                                },
                                shape = RoundedCornerShape(8.dp),
                                colors = ButtonDefaults.buttonColors(containerColor = StudioSurfaceCard)
                            ) {
                                Icon(Icons.Default.OpenInNew, contentDescription = null, tint = StudioPrimary, modifier = Modifier.size(14.dp))
                                Spacer(modifier = Modifier.width(4.dp))
                                Text("Open Link", fontSize = 11.sp, color = StudioPrimary)
                            }
                        }
                    }
                }
            }

            // Published Archive Section
            item {
                Spacer(modifier = Modifier.height(8.dp))
                Text(
                    text = "Published Archive (${state.publishedLog.size} Videos)",
                    style = MaterialTheme.typography.titleMedium,
                    color = TextPrimary,
                    fontWeight = FontWeight.Bold
                )
            }

            items(state.publishedLog, key = { it.videoId + it.id }) { pub ->
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clip(RoundedCornerShape(10.dp))
                        .background(StudioSurfaceDark)
                        .border(1.dp, BorderSubtle, RoundedCornerShape(10.dp))
                        .clickable {
                            val intent = Intent(Intent.ACTION_VIEW, Uri.parse(pub.url))
                            context.startActivity(intent)
                        }
                        .padding(12.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Box(
                        modifier = Modifier
                            .size(36.dp)
                            .clip(CircleShape)
                            .background(if (pub.kind == "short") StudioSecondary.copy(alpha = 0.2f) else StudioPrimary.copy(alpha = 0.2f)),
                        contentAlignment = Alignment.Center
                    ) {
                        Icon(
                            imageVector = if (pub.kind == "short") Icons.Default.Smartphone else Icons.Default.PlayArrow,
                            contentDescription = null,
                            tint = if (pub.kind == "short") StudioSecondary else StudioPrimary,
                            modifier = Modifier.size(18.dp)
                        )
                    }

                    Spacer(modifier = Modifier.width(12.dp))

                    Column(modifier = Modifier.weight(1f)) {
                        Text(
                            text = pub.title,
                            fontSize = 13.sp,
                            fontWeight = FontWeight.Bold,
                            color = TextPrimary,
                            maxLines = 1
                        )
                        Text(
                            text = "${pub.videoId} • ${pub.uploadedAt.take(10)}",
                            fontSize = 11.sp,
                            color = TextMuted
                        )
                    }

                    Icon(
                        imageVector = Icons.Default.ChevronRight,
                        contentDescription = "Details",
                        tint = TextMuted
                    )
                }
            }
        }

        // Run Details Dialog
        state.selectedRunForDetail?.let { run ->
            Dialog(onDismissRequest = { onSelectRun(null) }) {
                Card(
                    modifier = Modifier.fillMaxWidth(),
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
                            Text("Run Result Manifest", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold, color = TextPrimary)
                            IconButton(onClick = { onSelectRun(null) }) {
                                Icon(Icons.Default.Close, contentDescription = "Close", tint = TextSecondary)
                            }
                        }

                        HorizontalDivider(color = BorderSubtle, modifier = Modifier.padding(vertical = 10.dp))

                        Text("ID: ${run.id}", fontSize = 12.sp, color = StudioPrimary, fontWeight = FontWeight.Bold)
                        Text("Status: ${run.status}", fontSize = 12.sp, color = TextSecondary)
                        Text("Video ID: ${run.videoId}", fontSize = 12.sp, color = TextSecondary)
                        Text("Scheduled: ${run.scheduledFor}", fontSize = 12.sp, color = TextSecondary)
                        Text("Thumbnail: ${run.thumbnailStatus}", fontSize = 12.sp, color = StudioAccentAmber)
                        Text("Comments: ${run.commentStatus}", fontSize = 11.sp, color = TextMuted)

                        if (run.thumbPrompt.isNotBlank()) {
                            Spacer(modifier = Modifier.height(10.dp))
                            Text("ChatGPT / Neural Thumbnail Prompt:", fontSize = 11.sp, fontWeight = FontWeight.Bold, color = TextPrimary)
                            Box(
                                modifier = Modifier
                                    .fillMaxWidth()
                                    .clip(RoundedCornerShape(8.dp))
                                    .background(StudioSurfaceCard)
                                    .padding(10.dp)
                            ) {
                                Text(run.thumbPrompt, fontSize = 11.sp, color = TextSecondary)
                            }
                        }

                        Spacer(modifier = Modifier.height(14.dp))
                        Button(
                            onClick = {
                                val intent = Intent(Intent.ACTION_VIEW, Uri.parse(run.url))
                                context.startActivity(intent)
                            },
                            modifier = Modifier.fillMaxWidth(),
                            colors = ButtonDefaults.buttonColors(containerColor = StudioPrimary)
                        ) {
                            Text("Open in YouTube Browser", color = Color.Black, fontWeight = FontWeight.Bold)
                        }
                    }
                }
            }
        }
    }
}
