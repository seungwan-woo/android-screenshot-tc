package com.example.screenshotci;

import android.app.Activity;
import android.os.Bundle;
import android.graphics.Color;
import android.graphics.Typeface;
import android.view.Gravity;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;

public final class MainActivity extends Activity {
    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    private TextView text(String value, int size, int color) {
        TextView view = new TextView(this);
        view.setText(value);
        view.setTextSize(size);
        view.setTextColor(color);
        view.setPadding(0, dp(8), 0, dp(8));
        return view;
    }

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().setStatusBarColor(Color.rgb(245, 247, 251));
        getWindow().setNavigationBarColor(Color.rgb(245, 247, 251));
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setGravity(Gravity.CENTER_VERTICAL);
        root.setPadding(dp(28), dp(48), dp(28), dp(48));
        root.setBackgroundColor(Color.rgb(245, 247, 251));
        TextView heading = text("Screenshot CI", 32, Color.rgb(28, 40, 70));
        heading.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        root.addView(heading);
        root.addView(text("Full emulator display capture", 18, Color.rgb(74, 87, 110)));
        root.addView(text("Android 15 / API 35\n1080 x 1920 / 420 dpi", 16, Color.rgb(74, 87, 110)));
        TextView status = text("State: READY", 24, Color.rgb(13, 115, 83));
        status.setContentDescription("sample_state");
        root.addView(status);
        Button update = new Button(this);
        update.setText("Update state");
        update.setAllCaps(false);
        update.setContentDescription("update_state");
        update.setOnClickListener(view -> status.setText("State: UPDATED"));
        root.addView(update, new LinearLayout.LayoutParams(-1, dp(56)));
        root.addView(text("Same screen passes. Visual changes fail.", 14, Color.rgb(74, 87, 110)));
        setContentView(root);
    }
}
