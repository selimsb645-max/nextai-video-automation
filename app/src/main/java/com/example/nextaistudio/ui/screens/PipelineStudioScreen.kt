package com.example.nextaistudio.ui.screens

import android.content.Intent
import android.net.Uri
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.nextaistudio.ui.theme.*
import com.example.nextaistudio.ui.viewmodel.NextAIViewModel
import com.example.nextaistudio.ui.viewmodel.UiState

@Composable
fun PipelineStudioScreen(
    viewModel: NextAIViewModel,
    state: UiState
) {
    val studio = state.pipelineState
    val entry = studio.selectedEntry
    val context = LocalContext.current

    if (entry == null) {
        Box(
            modifier = Modifier
                .fillMaxSize()
                .background(StudioDarkBackground)
                .padding(24.dp),
            contentAlignment = Alignment.Center
        ) {
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                Icon(
                    imageVector = Icons.Default.VideoCall,
                    contentDescription = null,
                    tint = TextMuted,
                    modifier = Modifier.size(64.dp)
                )
                Spacer(modifier = Modifier.height(16.dp))
                Text(
                    text = "No Topic Selected",
                    style = MaterialTheme.typography.titleLarge,
                    color = TextPrimary,
                    fontWeight = FontWeight.Bold
                )
                Spacer(modifier = Modifier.height(8.dp))
                Text(
                    text = "Choose an eligible topic from the Content Library to launch the pipeline.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = TextSecondary,
                    textAlign = TextAlign.Center
                )
                Spacer(modifier = Modifier.height(20.dp))
                Button(
                    onClick = {
                        val firstEligible = state.libraryEntries.firstOrNull { viewModel.isEntryEligible(it) }
                        if (firstEligible != null) {
                            viewModel.startProductionForEntry(firstEligible)
                        }
                    },
                    colors = ButtonDefaults.buttonColors(containerColor = StudioPrimary)
                ) {
                    Text("Load Next Eligible Topic", color = Color.Black, fontWeight = FontWeight.Bold)
                }
            }
        }
        return
    }

    LazyColumn(
        modifier = Modifier
            .fillMaxSize()
            .background(StudioDarkBackground)
            .padding(horizontal = 16.dp),
        contentPadding = PaddingValues(top = 16.dp, bottom = 96.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp)
    ) {
        // Step Indicator Progress Bar
        item {
            Card(
                modifier = Modifier.fillMaxWidth(),
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
                        Text(
                            text = "Step ${studio.currentStep} of 6: ${getStepTitle(studio.currentStep)}",
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.Bold,
                            color = StudioPrimary
                        )
                        Text(
                            text = if (entry.isShort) "9:16 Short" else "16:9 Long",
                            fontSize = 11.sp,
                            color = StudioSecondary,
                            fontWeight = FontWeight.SemiBold
                        )
                    }

                    Spacer(modifier = Modifier.height(10.dp))
                    LinearProgressIndicator(
                        progress = { studio.progressPercent },
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(6.dp)
                            .clip(RoundedCornerShape(3.dp)),
                        color = StudioPrimary,
                        trackColor = StudioSurfaceCard
                    )

                    if (studio.isProcessing) {
                        Spacer(modifier = Modifier.height(8.dp))
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            CircularProgressIndicator(
                                modifier = Modifier.size(14.dp),
                                color = StudioPrimary,
                                strokeWidth = 2.dp
                            )
                            Spacer(modifier = Modifier.width(8.dp))
                            Text(
                                text = studio.progressMessage,
                                fontSize = 11.sp,
                                color = StudioPrimary
                            )
                        }
                    }
                }
            }
        }

        // STEP CONTENT
        when (studio.currentStep) {
            1 -> item { Step1TopicLock(entry) }
            2 -> item { Step2FootageMatch(studio.matchedClips) }
            3 -> item { Step3VoicePacing(entry, studio.voiceMood, studio.voiceSpeed, studio.estimatedAudioDuration) }
            4 -> item { Step4VideoComposite(entry, studio.matchedClips) }
            5 -> item {
                Step5ThumbnailStudio(
                    entry = entry,
                    hook = studio.generatedThumbnailHook,
                    accent = studio.thumbnailAccentWord,
                    isBlurFill = studio.isThumbnailBlurFill,
                    onUpdateHook = { h, a -> viewModel.updateThumbnailHook(h, a) },
                    onToggleBlurFill = { viewModel.toggleThumbnailBlurFill() }
                )
            }
            6 -> item {
                Step6YouTubeUpload(
                    entry = entry,
                    slot = studio.calculatedSlot,
                    isCompleted = studio.isCompleted,
                    finalResult = studio.finalRunResult,
                    onOpenYouTube = { url ->
                        val intent = Intent(Intent.ACTION_VIEW, Uri.parse(url))
                        context.startActivity(intent)
                    }
                )
            }
        }

        // Navigation Action Buttons
        item {
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(top = 8.dp),
                horizontalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                if (studio.currentStep > 1 && !studio.isProcessing) {
                    OutlinedButton(
                        onClick = { viewModel.previousPipelineStep() },
                        modifier = Modifier.weight(1f),
                        shape = RoundedCornerShape(10.dp)
                    ) {
                        Icon(Icons.Default.ArrowBack, contentDescription = null, modifier = Modifier.size(16.dp))
                        Spacer(modifier = Modifier.width(6.dp))
                        Text("Previous")
                    }
                }

                if (studio.currentStep < 6 && !studio.isProcessing) {
                    Button(
                        onClick = { viewModel.nextPipelineStep() },
                        modifier = Modifier.weight(1f),
                        shape = RoundedCornerShape(10.dp),
                        colors = ButtonDefaults.buttonColors(containerColor = StudioPrimary)
                    ) {
                        Text("Next Step", color = Color.Black, fontWeight = FontWeight.Bold)
                        Spacer(modifier = Modifier.width(6.dp))
                        Icon(Icons.Default.ArrowForward, contentDescription = null, tint = Color.Black, modifier = Modifier.size(16.dp))
                    }
                } else if (studio.currentStep == 6 && !studio.isCompleted) {
                    Button(
                        onClick = { viewModel.executePipelineGeneration() },
                        enabled = !studio.isProcessing,
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(50.dp)
                            .testTag("execute_pipeline_button"),
                        shape = RoundedCornerShape(10.dp),
                        colors = ButtonDefaults.buttonColors(containerColor = StudioAccentGreen)
                    ) {
                        if (studio.isProcessing) {
                            CircularProgressIndicator(modifier = Modifier.size(20.dp), color = Color.White)
                            Spacer(modifier = Modifier.width(10.dp))
                            Text("Running Pipeline...", color = Color.White)
                        } else {
                            Icon(Icons.Default.CloudUpload, contentDescription = null, tint = Color.Black)
                            Spacer(modifier = Modifier.width(8.dp))
                            Text("Render & Schedule to YouTube", color = Color.Black, fontWeight = FontWeight.Bold)
                        }
                    }
                }
            }
        }
    }
}

private fun getStepTitle(step: Int): String = when (step) {
    1 -> "Topic Blueprint"
    2 -> "Semantic Footage"
    3 -> "Kokoro Voice"
    4 -> "Visual Composite"
    5 -> "Thumbnail Studio"
    6 -> "Schedule & Upload"
    else -> ""
}

@Composable
private fun Step1TopicLock(entry: com.example.nextaistudio.data.model.ContentEntry) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(14.dp),
        colors = CardDefaults.cardColors(containerColor = StudioSurfaceDark),
        border = CardDefaults.outlinedCardBorder().copy(brush = androidx.compose.ui.graphics.SolidColor(BorderSubtle))
    ) {
        Column(modifier = Modifier.padding(18.dp)) {
            Text(text = "Production Blueprint", fontSize = 12.sp, color = StudioPrimary, fontWeight = FontWeight.Bold)
            Spacer(modifier = Modifier.height(6.dp))
            Text(text = entry.title, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold, color = TextPrimary)
            Spacer(modifier = Modifier.height(10.dp))

            Text(text = entry.description, fontSize = 13.sp, color = TextSecondary, lineHeight = 18.sp)
            Spacer(modifier = Modifier.height(14.dp))

            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                PillTag("Pillar: ${entry.contentPillar}")
                PillTag("Format: ${if (entry.isShort) "9:16 Short" else "16:9 Long"}")
                PillTag("${entry.wordCount} words")
            }

            Spacer(modifier = Modifier.height(14.dp))
            Text(text = "Editorial Scope Review:", fontSize = 11.sp, fontWeight = FontWeight.Bold, color = TextPrimary)
            Spacer(modifier = Modifier.height(4.dp))
            Text(text = "• Sources: ${entry.verifiedSources.joinToString(", ")}", fontSize = 11.sp, color = TextSecondary)
            Text(text = "• Evidence: ${entry.demandEvidence}", fontSize = 11.sp, color = StudioAccentGreen)
            Text(text = "• Zero hands-on testing claims without hardware; evidence-based comparison only.", fontSize = 11.sp, color = TextMuted)
        }
    }
}

@Composable
private fun Step2FootageMatch(matchedClips: List<Pair<com.example.nextaistudio.data.model.Beat, com.example.nextaistudio.data.model.FootageClip>>) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(14.dp),
        colors = CardDefaults.cardColors(containerColor = StudioSurfaceDark),
        border = CardDefaults.outlinedCardBorder().copy(brush = androidx.compose.ui.graphics.SolidColor(BorderSubtle))
    ) {
        Column(modifier = Modifier.padding(18.dp)) {
            Text(text = "Strict Semantic Footage Matching", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, color = TextPrimary)
            Spacer(modifier = Modifier.height(4.dp))
            Text(text = "Zero clip repeats constraint across all video beats. Pexels licensed pool.", fontSize = 12.sp, color = TextSecondary)
            Spacer(modifier = Modifier.height(14.dp))

            matchedClips.forEachIndexed { i, (beat, clip) ->
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(vertical = 4.dp)
                        .clip(RoundedCornerShape(8.dp))
                        .background(StudioSurfaceCard)
                        .padding(10.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Box(
                        modifier = Modifier
                            .size(24.dp)
                            .clip(CircleShape)
                            .background(StudioPrimary.copy(alpha = 0.2f)),
                        contentAlignment = Alignment.Center
                    ) {
                        Text(text = "${i + 1}", fontSize = 11.sp, fontWeight = FontWeight.Bold, color = StudioPrimary)
                    }
                    Spacer(modifier = Modifier.width(10.dp))
                    Column(modifier = Modifier.weight(1f)) {
                        Text(text = beat.t, fontSize = 12.sp, color = TextPrimary, maxLines = 1)
                        Text(text = "Pool clip: ${clip.file} [${clip.category}]", fontSize = 10.sp, color = StudioSecondary)
                    }
                    Icon(Icons.Default.CheckCircle, contentDescription = "Matched", tint = StudioAccentGreen, modifier = Modifier.size(16.dp))
                }
            }
        }
    }
}

@Composable
private fun Step3VoicePacing(
    entry: com.example.nextaistudio.data.model.ContentEntry,
    mood: String,
    speed: Double,
    estimatedAudioDuration: Double
) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(14.dp),
        colors = CardDefaults.cardColors(containerColor = StudioSurfaceDark),
        border = CardDefaults.outlinedCardBorder().copy(brush = androidx.compose.ui.graphics.SolidColor(BorderSubtle))
    ) {
        Column(modifier = Modifier.padding(18.dp)) {
            Text(text = "Kokoro Voice Synthesis (am_michael)", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, color = TextPrimary)
            Spacer(modifier = Modifier.height(4.dp))
            Text(text = "Human-like documentary pacing with emotion detection and natural beat pauses.", fontSize = 12.sp, color = TextSecondary)
            Spacer(modifier = Modifier.height(14.dp))

            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                VoiceMetric(modifier = Modifier.weight(1f), label = "Voice Profile", value = "am_michael (Kokoro)")
                VoiceMetric(modifier = Modifier.weight(1f), label = "Detected Mood", value = mood)
            }
            Spacer(modifier = Modifier.height(8.dp))
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                VoiceMetric(modifier = Modifier.weight(1f), label = "Speaking Speed", value = "${String.format("%.2f", speed)}x")
                VoiceMetric(modifier = Modifier.weight(1f), label = "Est. Duration", value = "${estimatedAudioDuration.toInt()}s")
            }

            Spacer(modifier = Modifier.height(14.dp))
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .clip(RoundedCornerShape(8.dp))
                    .background(if (entry.isShort && estimatedAudioDuration > 60) StudioAccentRed.copy(alpha = 0.2f) else StudioAccentGreen.copy(alpha = 0.15f))
                    .padding(10.dp)
            ) {
                Text(
                    text = if (entry.isShort && estimatedAudioDuration > 60)
                        "CRITICAL: Duration exceeds 60s vertical Shorts gate (${estimatedAudioDuration.toInt()}s)! Truncate narration."
                    else
                        "✓ Duration conforms to YouTube format specifications (${if (entry.isShort) "< 60s Shorts gate" else "16:9 Long"} verified).",
                    fontSize = 11.sp,
                    color = if (entry.isShort && estimatedAudioDuration > 60) StudioAccentRed else StudioAccentGreen,
                    fontWeight = FontWeight.SemiBold
                )
            }
        }
    }
}

@Composable
private fun Step4VideoComposite(
    entry: com.example.nextaistudio.data.model.ContentEntry,
    clips: List<Pair<com.example.nextaistudio.data.model.Beat, com.example.nextaistudio.data.model.FootageClip>>
) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(14.dp),
        colors = CardDefaults.cardColors(containerColor = StudioSurfaceDark),
        border = CardDefaults.outlinedCardBorder().copy(brush = androidx.compose.ui.graphics.SolidColor(BorderSubtle))
    ) {
        Column(modifier = Modifier.padding(18.dp)) {
            Text(text = "Visual Composite & Ambient Bed", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, color = TextPrimary)
            Spacer(modifier = Modifier.height(4.dp))
            Text(text = "Multi-clip crossfades (xfade=0.6s) + Harmonic chord bed + Loudnorm I=-13", fontSize = 12.sp, color = TextSecondary)
            Spacer(modifier = Modifier.height(14.dp))

            // Video Canvas Preview Simulator
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .height(200.dp)
                    .clip(RoundedCornerShape(10.dp))
                    .background(Color.Black),
                contentAlignment = Alignment.Center
            ) {
                Canvas(modifier = Modifier.fillMaxSize()) {
                    // Draw cinematic grade background
                    drawRect(color = Color(0xFF0F172A))

                    // Draw subtle grid overlay
                    val step = 40f
                    for (x in 0..(size.width / step).toInt()) {
                        drawLine(
                            color = Color(0xFF1E293B),
                            start = Offset(x * step, 0f),
                            end = Offset(x * step, size.height),
                            strokeWidth = 1f
                        )
                    }

                    // Draw simulated audio waveform bed (harmonic chords 110Hz + 164Hz)
                    val midY = size.height * 0.75f
                    val wavePoints = 50
                    for (i in 0 until wavePoints) {
                        val x = (size.width / wavePoints) * i
                        val h = kotlin.math.sin(i * 0.4) * 22f + kotlin.math.sin(i * 0.8) * 12f
                        drawLine(
                            color = StudioPrimary.copy(alpha = 0.7f),
                            start = Offset(x, midY - h.toFloat()),
                            end = Offset(x, midY + h.toFloat()),
                            strokeWidth = 3f
                        )
                    }

                    // Vignette circle border
                    drawCircle(
                        color = Color.Black.copy(alpha = 0.35f),
                        radius = size.width * 0.6f,
                        center = Offset(size.width / 2, size.height / 2),
                        style = Stroke(width = 80f)
                    )
                }

                // Subtitle Overlay
                Column(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(12.dp),
                    verticalArrangement = Arrangement.SpaceBetween,
                    horizontalAlignment = Alignment.CenterHorizontally
                ) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Box(
                            modifier = Modifier
                                .clip(RoundedCornerShape(4.dp))
                                .background(StudioAccentRed)
                                .padding(horizontal = 6.dp, vertical = 2.dp)
                        ) {
                            Text("NEXTAI VISION", fontSize = 9.sp, fontWeight = FontWeight.Bold, color = Color.White)
                        }
                        Text("25 FPS • 1080p • CRF 21", fontSize = 9.sp, color = TextSecondary)
                    }

                    Box(
                        modifier = Modifier
                            .fillMaxWidth(0.9f)
                            .clip(RoundedCornerShape(6.dp))
                            .background(Color.Black.copy(alpha = 0.8f))
                            .padding(horizontal = 10.dp, vertical = 6.dp),
                        contentAlignment = Alignment.Center
                    ) {
                        Text(
                            text = clips.firstOrNull()?.first?.t ?: entry.title,
                            fontSize = 11.sp,
                            color = Color.White,
                            textAlign = TextAlign.Center,
                            maxLines = 2
                        )
                    }
                }
            }

            Spacer(modifier = Modifier.height(10.dp))
            Text(
                text = "Audio Bed: Harmonic Chords [110Hz, 164Hz, 220Hz] + Brown Noise (amp 0.012) + Loudnorm",
                fontSize = 10.sp,
                color = TextMuted
            )
        }
    }
}

@Composable
private fun Step5ThumbnailStudio(
    entry: com.example.nextaistudio.data.model.ContentEntry,
    hook: String,
    accent: String,
    isBlurFill: Boolean,
    onUpdateHook: (String, String) -> Unit,
    onToggleBlurFill: () -> Unit
) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(14.dp),
        colors = CardDefaults.cardColors(containerColor = StudioSurfaceDark),
        border = CardDefaults.outlinedCardBorder().copy(brush = androidx.compose.ui.graphics.SolidColor(BorderSubtle))
    ) {
        Column(modifier = Modifier.padding(18.dp)) {
            Text(text = "Thumbnail Studio (Neural / Nate Style)", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, color = TextPrimary)
            Spacer(modifier = Modifier.height(4.dp))
            Text(text = "Clean dark background, 2-5 words bold sans-serif hook, factual red accent word.", fontSize = 12.sp, color = TextSecondary)
            Spacer(modifier = Modifier.height(14.dp))

            // Live 16:9 Thumbnail Canvas
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .aspectRatio(16f / 9f)
                    .clip(RoundedCornerShape(10.dp))
                    .background(Color(0xFF090D16))
                    .border(1.dp, BorderSubtle, RoundedCornerShape(10.dp)),
                contentAlignment = Alignment.Center
            ) {
                // Background visual cue
                Canvas(modifier = Modifier.fillMaxSize()) {
                    drawCircle(
                        color = StudioPrimary.copy(alpha = 0.12f),
                        radius = size.width * 0.35f,
                        center = Offset(size.width * 0.75f, size.height * 0.5f)
                    )
                }

                Column(
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(16.dp),
                    verticalArrangement = Arrangement.SpaceBetween
                ) {
                    Box(
                        modifier = Modifier
                            .clip(RoundedCornerShape(4.dp))
                            .background(StudioAccentRed)
                            .padding(horizontal = 8.dp, vertical = 3.dp)
                    ) {
                        Text("NEXTAI VISION", fontSize = 10.sp, fontWeight = FontWeight.Bold, color = Color.White)
                    }

                    Column {
                        Text(
                            text = hook,
                            fontSize = 20.sp,
                            fontWeight = FontWeight.Black,
                            color = Color.White,
                            lineHeight = 24.sp
                        )
                        Text(
                            text = accent,
                            fontSize = 22.sp,
                            fontWeight = FontWeight.Black,
                            color = StudioAccentRed,
                            lineHeight = 26.sp
                        )
                    }
                }
            }

            Spacer(modifier = Modifier.height(14.dp))

            // Customization Text Fields
            OutlinedTextField(
                value = hook,
                onValueChange = { onUpdateHook(it, accent) },
                label = { Text("Primary Hook (White Text)") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
                colors = OutlinedTextFieldDefaults.colors(
                    focusedTextColor = TextPrimary,
                    unfocusedTextColor = TextPrimary
                )
            )

            Spacer(modifier = Modifier.height(8.dp))

            OutlinedTextField(
                value = accent,
                onValueChange = { onUpdateHook(hook, it) },
                label = { Text("Accent Word (Red Highlight)") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
                colors = OutlinedTextFieldDefaults.colors(
                    focusedTextColor = TextPrimary,
                    unfocusedTextColor = TextPrimary
                )
            )

            if (entry.isShort) {
                Spacer(modifier = Modifier.height(10.dp))
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        text = "Blur-fill to 1280x720 (YouTube requirement)",
                        fontSize = 12.sp,
                        color = TextSecondary
                    )
                    Switch(
                        checked = isBlurFill,
                        onCheckedChange = { onToggleBlurFill() }
                    )
                }
            }
        }
    }
}

@Composable
private fun Step6YouTubeUpload(
    entry: com.example.nextaistudio.data.model.ContentEntry,
    slot: com.example.nextaistudio.data.model.ScheduleSlot?,
    isCompleted: Boolean,
    finalResult: com.example.nextaistudio.data.model.RunResult?,
    onOpenYouTube: (String) -> Unit
) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(14.dp),
        colors = CardDefaults.cardColors(containerColor = StudioSurfaceDark),
        border = CardDefaults.outlinedCardBorder().copy(brush = androidx.compose.ui.graphics.SolidColor(BorderSubtle))
    ) {
        Column(modifier = Modifier.padding(18.dp)) {
            Text(text = "YouTube Resumable Upload & Schedule", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold, color = TextPrimary)
            Spacer(modifier = Modifier.height(4.dp))
            Text(text = "Scheduled private with publishAt strictly 8–10 hours ahead.", fontSize = 12.sp, color = TextSecondary)
            Spacer(modifier = Modifier.height(14.dp))

            if (isCompleted && finalResult != null) {
                // Success banner
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clip(RoundedCornerShape(10.dp))
                        .background(StudioAccentGreen.copy(alpha = 0.15f))
                        .border(1.dp, StudioAccentGreen, RoundedCornerShape(10.dp))
                        .padding(14.dp)
                ) {
                    Column {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Icon(Icons.Default.CheckCircle, contentDescription = null, tint = StudioAccentGreen)
                            Spacer(modifier = Modifier.width(8.dp))
                            Text("Scheduled Successfully on YouTube", fontWeight = FontWeight.Bold, color = StudioAccentGreen)
                        }
                        Spacer(modifier = Modifier.height(6.dp))
                        Text("Video ID: ${finalResult.videoId}", fontSize = 12.sp, color = TextPrimary)
                        Text("Scheduled For: ${finalResult.scheduledFor} (${slot?.timeLabel})", fontSize = 12.sp, color = TextSecondary)
                        Text("Privacy: private (auto-publishes on slot)", fontSize = 11.sp, color = TextMuted)
                        Spacer(modifier = Modifier.height(10.dp))
                        Button(
                            onClick = { onOpenYouTube(finalResult.url) },
                            colors = ButtonDefaults.buttonColors(containerColor = StudioPrimary)
                        ) {
                            Icon(Icons.Default.OpenInNew, contentDescription = null, tint = Color.Black, modifier = Modifier.size(16.dp))
                            Spacer(modifier = Modifier.width(6.dp))
                            Text("Open on YouTube", color = Color.Black, fontWeight = FontWeight.Bold)
                        }
                    }
                }
            } else {
                Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    VoiceMetric(modifier = Modifier.weight(1f), label = "Target BD Slot", value = slot?.timeLabel ?: "19:30 BST")
                    VoiceMetric(modifier = Modifier.weight(1f), label = "Lead Hours Gap", value = "${String.format("%.1f", slot?.gapHours ?: 8.5)}h ahead")
                }

                Spacer(modifier = Modifier.height(14.dp))
                Text(text = "SEO Metadata & Tags Preview:", fontSize = 11.sp, fontWeight = FontWeight.Bold, color = TextPrimary)
                Spacer(modifier = Modifier.height(4.dp))
                Box(
                    modifier = Modifier
                        .fillMaxWidth()
                        .clip(RoundedCornerShape(8.dp))
                        .background(StudioSurfaceCard)
                        .padding(10.dp)
                ) {
                    Text(
                        text = "Tags: ${entry.tags.take(6).joinToString(", ")}\n\nDisclaimer: This video includes AI-generated visuals and voiceover for educational purposes.",
                        fontSize = 11.sp,
                        color = TextSecondary
                    )
                }
            }
        }
    }
}

@Composable
private fun PillTag(text: String) {
    Box(
        modifier = Modifier
            .clip(RoundedCornerShape(6.dp))
            .background(StudioSurfaceCard)
            .padding(horizontal = 8.dp, vertical = 4.dp)
    ) {
        Text(text = text, fontSize = 11.sp, color = TextSecondary)
    }
}

@Composable
private fun VoiceMetric(modifier: Modifier = Modifier, label: String, value: String) {
    Box(
        modifier = modifier
            .clip(RoundedCornerShape(8.dp))
            .background(StudioSurfaceCard)
            .padding(10.dp)
    ) {
        Column {
            Text(text = label, fontSize = 10.sp, color = TextMuted)
            Spacer(modifier = Modifier.height(2.dp))
            Text(text = value, fontSize = 12.sp, fontWeight = FontWeight.Bold, color = TextPrimary)
        }
    }
}
