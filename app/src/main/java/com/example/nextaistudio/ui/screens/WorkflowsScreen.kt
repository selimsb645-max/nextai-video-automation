package com.example.nextaistudio.ui.screens

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.nextaistudio.data.model.WorkflowTemplate
import com.example.nextaistudio.ui.theme.*
import com.example.nextaistudio.ui.viewmodel.UiState

@Composable
fun WorkflowsScreen(
    state: UiState,
    onToggleWorkflow: (String) -> Unit
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
                    text = "Automated Workflows",
                    style = MaterialTheme.typography.headlineMedium,
                    color = TextPrimary,
                    fontWeight = FontWeight.Bold
                )
                Text(
                    text = "Portable automation templates and schedule guards",
                    style = MaterialTheme.typography.bodyMedium,
                    color = TextSecondary
                )
            }
        }

        items(state.workflowTemplates, key = { it.id }) { wf ->
            Card(
                modifier = Modifier
                    .fillMaxWidth()
                    .testTag("workflow_card_${wf.id}"),
                shape = RoundedCornerShape(14.dp),
                colors = CardDefaults.cardColors(containerColor = StudioSurfaceDark),
                border = CardDefaults.outlinedCardBorder().copy(brush = androidx.compose.ui.graphics.SolidColor(BorderSubtle))
            ) {
                Column(modifier = Modifier.padding(18.dp)) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Column(modifier = Modifier.weight(1f)) {
                            Text(
                                text = wf.name,
                                style = MaterialTheme.typography.titleMedium,
                                fontWeight = FontWeight.Bold,
                                color = TextPrimary
                            )
                            Spacer(modifier = Modifier.height(2.dp))
                            Text(
                                text = "Cron: ${wf.cron} • ${wf.triggerDhakaTime}",
                                fontSize = 11.sp,
                                color = StudioPrimary
                            )
                        }

                        Switch(
                            checked = wf.isActive,
                            onCheckedChange = { onToggleWorkflow(wf.id) }
                        )
                    }

                    Spacer(modifier = Modifier.height(10.dp))
                    Text(
                        text = wf.description,
                        fontSize = 12.sp,
                        color = TextSecondary,
                        lineHeight = 16.sp
                    )

                    Spacer(modifier = Modifier.height(12.dp))
                    Text(
                        text = "Guard Rules:",
                        fontSize = 11.sp,
                        fontWeight = FontWeight.Bold,
                        color = TextPrimary
                    )
                    Spacer(modifier = Modifier.height(4.dp))
                    Column(verticalArrangement = Arrangement.spacedBy(3.dp)) {
                        wf.guardRules.forEach { rule ->
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Box(
                                    modifier = Modifier
                                        .size(4.dp)
                                        .clip(RoundedCornerShape(2.dp))
                                        .background(if (wf.isActive) StudioAccentGreen else TextMuted)
                                )
                                Spacer(modifier = Modifier.width(6.dp))
                                Text(text = rule, fontSize = 11.sp, color = TextMuted)
                            }
                        }
                    }
                }
            }
        }
    }
}
