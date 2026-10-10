package com.example.nextaistudio.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.nextaistudio.ui.theme.*

@Composable
fun PolicyScreen() {
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
                    text = "Editorial Policy & Guidelines",
                    style = MaterialTheme.typography.headlineMedium,
                    color = TextPrimary,
                    fontWeight = FontWeight.Bold
                )
                Text(
                    text = "Strict production scope & reference rules (factory/content_policy.json)",
                    style = MaterialTheme.typography.bodyMedium,
                    color = TextSecondary
                )
            }
        }

        // Allowed Content Pillars
        item {
            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(14.dp),
                colors = CardDefaults.cardColors(containerColor = StudioSurfaceDark),
                border = CardDefaults.outlinedCardBorder().copy(brush = androidx.compose.ui.graphics.SolidColor(BorderSubtle))
            ) {
                Column(modifier = Modifier.padding(18.dp)) {
                    Text(
                        text = "Allowed Content Pillars (3 Only)",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold,
                        color = StudioPrimary
                    )
                    Spacer(modifier = Modifier.height(10.dp))
                    PillarItem(
                        title = "1. AI Tool & Platform Updates",
                        desc = "ChatGPT, OpenAI, Claude, Anthropic, Gemini, Google AI Studio, Grok, DeepSeek, Qwen. Feature comparisons and practical developer workflows."
                    )
                    Spacer(modifier = Modifier.height(8.dp))
                    PillarItem(
                        title = "2. Evidence-Based Gadget Reviews",
                        desc = "Spec-based buying guides. Never claim hands-on testing or present generic stock footage as the actual reviewed device."
                    )
                    Spacer(modifier = Modifier.height(8.dp))
                    PillarItem(
                        title = "3. General Personal Finance",
                        desc = "General education only (HYSA, savings rates, fee comparisons). No personalized investment advice or guaranteed returns."
                    )
                }
            }
        }

        // Production Style References
        item {
            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(14.dp),
                colors = CardDefaults.cardColors(containerColor = StudioSurfaceDark),
                border = CardDefaults.outlinedCardBorder().copy(brush = androidx.compose.ui.graphics.SolidColor(BorderSubtle))
            ) {
                Column(modifier = Modifier.padding(18.dp)) {
                    Text(
                        text = "Production Style: Nate B Jones & Neural Nutshell",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold,
                        color = TextPrimary
                    )
                    Spacer(modifier = Modifier.height(10.dp))

                    Text(
                        text = "Video Tone & Structure:",
                        fontSize = 12.sp,
                        fontWeight = FontWeight.Bold,
                        color = StudioSecondary
                    )
                    Text(
                        text = "• Immediate specific thesis/hook grounded in verified facts\n" +
                                "• Explain the update and why it matters for the viewer\n" +
                                "• Provide verified practical comparison with attributed evidence\n" +
                                "• Transparently explain limitations and tradeoffs\n" +
                                "• End with useful takeaway and short subscribe CTA",
                        fontSize = 12.sp,
                        color = TextSecondary,
                        lineHeight = 18.sp
                    )

                    Spacer(modifier = Modifier.height(12.dp))
                    Text(
                        text = "Thumbnail Design Rules:",
                        fontSize = 12.sp,
                        fontWeight = FontWeight.Bold,
                        color = StudioSecondary
                    )
                    Text(
                        text = "• Near-black / deep navy documentary-tech background with generous negative space\n" +
                                "• One clear central focal subject (no visual clutter)\n" +
                                "• 2–5 words flat white condensed sans-serif hook text\n" +
                                "• One crisp factual RED accent word\n" +
                                "• Strict Face Rule: No creator likenesses, borrowed portraits, or fake experts",
                        fontSize = 12.sp,
                        color = TextSecondary,
                        lineHeight = 18.sp
                    )
                }
            }
        }

        // Schedule & Cost Constraints
        item {
            Card(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(14.dp),
                colors = CardDefaults.cardColors(containerColor = StudioSurfaceDark),
                border = CardDefaults.outlinedCardBorder().copy(brush = androidx.compose.ui.graphics.SolidColor(BorderSubtle))
            ) {
                Column(modifier = Modifier.padding(18.dp)) {
                    Text(
                        text = "Schedules & Zero-Cost Constraints",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold,
                        color = TextPrimary
                    )
                    Spacer(modifier = Modifier.height(10.dp))

                    Text(
                        text = "• Asia/Dhaka (BST) clock is authoritative\n" +
                                "• Daily Output: 2 Longs (19:30, 23:30) and 3 Shorts (02:30, 06:30, 22:00)\n" +
                                "• Lead time strictly 8–10 hours ahead; fail-closed if missed\n" +
                                "• No Long-to-Short recycling; each Short is an independent original piece\n" +
                                "• Zero-cost stack: Free Pexels footage + Kokoro voice + FFmpeg\n" +
                                "• Preserved active uploads (OISJ6w_gFKE, o4LMHDzIWec, vLbiHvf4XYo) must never be re-uploaded",
                        fontSize = 12.sp,
                        color = TextSecondary,
                        lineHeight = 18.sp
                    )
                }
            }
        }
    }
}

@Composable
private fun PillarItem(title: String, desc: String) {
    Column {
        Text(text = title, fontSize = 13.sp, fontWeight = FontWeight.Bold, color = TextPrimary)
        Spacer(modifier = Modifier.height(2.dp))
        Text(text = desc, fontSize = 11.sp, color = TextSecondary, lineHeight = 16.sp)
    }
}
