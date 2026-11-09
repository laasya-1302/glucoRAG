package com.gpformer.glucosetransmitter.ui

import android.graphics.Color
import android.view.LayoutInflater
import android.view.ViewGroup
import androidx.core.content.ContextCompat
import androidx.recyclerview.widget.DiffUtil
import androidx.recyclerview.widget.ListAdapter
import androidx.recyclerview.widget.RecyclerView
import com.gpformer.glucosetransmitter.R
import com.gpformer.glucosetransmitter.databinding.ItemGlucoseReadingBinding
import com.gpformer.glucosetransmitter.model.GlucoseReading

/**
 * Modern RecyclerView Adapter displaying the 24 rolling glucose readings.
 * Color-codes risk bands and clearly tags simulated vs manual entries.
 */
class ReadingHistoryAdapter :
    ListAdapter<GlucoseReading, ReadingHistoryAdapter.ReadingViewHolder>(DiffCallback) {

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ReadingViewHolder {
        val binding = ItemGlucoseReadingBinding.inflate(
            LayoutInflater.from(parent.context),
            parent,
            false
        )
        return ReadingViewHolder(binding)
    }

    override fun onBindViewHolder(holder: ReadingViewHolder, position: Int) {
        holder.bind(getItem(position))
    }

    class ReadingViewHolder(
        private val binding: ItemGlucoseReadingBinding
    ) : RecyclerView.ViewHolder(binding.root) {

        fun bind(reading: GlucoseReading) {
            binding.tvSequence.text = "#${reading.sequence}"
            binding.tvGlucoseValue.text = "${reading.glucose}"
            binding.tvUnit.text = reading.unit
            binding.tvTimestamp.text = reading.timestamp

            // Source indicator
            binding.tvSourceBadge.text = reading.source.uppercase()
            if (reading.source == GlucoseReading.SOURCE_SIMULATED) {
                binding.tvSourceBadge.setBackgroundColor(Color.parseColor("#4A148C")) // Deep purple
                binding.tvSourceBadge.setTextColor(Color.WHITE)
            } else {
                binding.tvSourceBadge.setBackgroundColor(Color.parseColor("#004D40")) // Dark teal
                binding.tvSourceBadge.setTextColor(Color.WHITE)
            }

            // Physiological risk band indicator
            when (reading.riskCategory) {
                GlucoseReading.RiskCategory.HYPO -> {
                    binding.tvRiskBadge.text = "HYPO (<70)"
                    binding.tvRiskBadge.setTextColor(Color.parseColor("#D32F2F"))
                    binding.cardIndicator.setBackgroundColor(Color.parseColor("#D32F2F"))
                }
                GlucoseReading.RiskCategory.NORMAL -> {
                    binding.tvRiskBadge.text = "NORMAL (70-180)"
                    binding.tvRiskBadge.setTextColor(Color.parseColor("#2E7D32"))
                    binding.cardIndicator.setBackgroundColor(Color.parseColor("#2E7D32"))
                }
                GlucoseReading.RiskCategory.HYPER -> {
                    binding.tvRiskBadge.text = "HYPER (>180)"
                    binding.tvRiskBadge.setTextColor(Color.parseColor("#EF6C00"))
                    binding.cardIndicator.setBackgroundColor(Color.parseColor("#EF6C00"))
                }
            }
        }
    }

    companion object DiffCallback : DiffUtil.ItemCallback<GlucoseReading>() {
        override fun areItemsTheSame(oldItem: GlucoseReading, newItem: GlucoseReading): Boolean {
            return oldItem.sequence == newItem.sequence
        }

        override fun areContentsTheSame(oldItem: GlucoseReading, newItem: GlucoseReading): Boolean {
            return oldItem == newItem
        }
    }
}
