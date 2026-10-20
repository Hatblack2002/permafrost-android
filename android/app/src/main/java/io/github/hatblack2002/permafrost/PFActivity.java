package io.github.hatblack2002.permafrost;

import android.app.Activity;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.graphics.Color;
import android.graphics.Typeface;
import android.os.Bundle;
import android.os.CountDownLatch;
import android.util.Log;
import android.view.Gravity;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import org.libsdl.app.SDLActivity;

/**
 * PFActivity — launcher subclass of SDL's SDLActivity for the Permafrost
 * Engine Android port.
 *
 * Adds a no-adb boot diagnostics path: when the native boot glue detects
 * a failed engine boot (non-zero exit code from the engine main), it
 * calls {@link #showBootReport} through JNI on the SDL thread. The report
 * (exit code + captured engine stderr/stdout/SDL log lines) is rendered
 * full-screen with a "Copiar registro" button (clipboard) so a failed
 * boot is diagnosable from a screenshot or a pasted text alone.
 *
 * Java-side uncaught exceptions are also logged to the on-screen report
 * path when possible (file + logcat; the process may be going down).
 */
public class PFActivity extends SDLActivity {

    private static final String TAG = "PFActivity";

    /** Called from native (SDL thread) via JNI: pf_android_main.c. */
    public static void showBootReport(final int exitCode, final String log) {
        final Activity act = mSingleton;
        if (act == null || act.isFinishing()) {
            Log.e(TAG, "boot report (exit " + exitCode + "): " + log);
            return;
        }
        final CountDownLatch latch = new CountDownLatch(1);

        act.runOnUiThread(new Runnable() {
            @Override
            public void run() {
                try {
                    ViewGroup content = act.findViewById(android.R.id.content);
                    if (content == null) {
                        latch.countDown();
                        return;
                    }

                    LinearLayout box = new LinearLayout(act);
                    box.setOrientation(LinearLayout.VERTICAL);
                    box.setBackgroundColor(Color.rgb(12, 12, 16));
                    box.setPadding(24, 24, 24, 24);

                    TextView title = new TextView(act);
                    title.setText("Permafrost — informe de arranque");
                    title.setTextColor(Color.rgb(255, 196, 96));
                    title.setTypeface(Typeface.MONOSPACE, Typeface.BOLD);
                    title.setTextSize(15);
                    title.setPadding(0, 8, 0, 16);

                    TextView tv = new TextView(act);
                    tv.setText(log == null || log.isEmpty()
                            ? "(sin registros capturados)" : log);
                    tv.setTextColor(Color.rgb(220, 220, 220));
                    tv.setTypeface(Typeface.MONOSPACE);
                    tv.setTextSize(11);
                    tv.setTextIsSelectable(true);

                    ScrollView scroll = new ScrollView(act);
                    scroll.addView(tv, new ViewGroup.LayoutParams(
                            ViewGroup.LayoutParams.MATCH_PARENT,
                            ViewGroup.LayoutParams.WRAP_CONTENT));

                    LinearLayout buttons = new LinearLayout(act);
                    buttons.setOrientation(LinearLayout.HORIZONTAL);
                    buttons.setGravity(Gravity.END);

                    Button copy = new Button(act);
                    copy.setText("Copiar registro");
                    copy.setOnClickListener(new android.view.View.OnClickListener() {
                        @Override
                        public void onClick(android.view.View v) {
                            try {
                                ClipboardManager cm = (ClipboardManager)
                                        act.getSystemService(CLIPBOARD_SERVICE);
                                cm.setPrimaryClip(ClipData.newPlainText(
                                        "pf-boot", log == null ? "" : log));
                                Toast.makeText(act, "Registro copiado",
                                        Toast.LENGTH_SHORT).show();
                            } catch (Throwable t) {
                                Log.e(TAG, "copy failed", t);
                            }
                        }
                    });

                    Button close = new Button(act);
                    close.setText("Cerrar");
                    close.setOnClickListener(new android.view.View.OnClickListener() {
                        @Override
                        public void onClick(android.view.View v) {
                            latch.countDown();
                        }
                    });

                    buttons.addView(copy);
                    buttons.addView(close);

                    box.addView(title);
                    box.addView(scroll, new LinearLayout.LayoutParams(
                            ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f));
                    box.addView(buttons, new LinearLayout.LayoutParams(
                            ViewGroup.LayoutParams.MATCH_PARENT,
                            ViewGroup.LayoutParams.WRAP_CONTENT));

                    content.addView(box, new ViewGroup.LayoutParams(
                            ViewGroup.LayoutParams.MATCH_PARENT,
                            ViewGroup.LayoutParams.MATCH_PARENT));
                } catch (Throwable t) {
                    Log.e(TAG, "failed to show boot report", t);
                    latch.countDown();
                }
            }
        });

        // Blocks the SDL thread until the user dismisses the report, so
        // SDLMain.run() does not finish() the activity out from under it.
        try {
            latch.await();
        } catch (InterruptedException ignored) {
        }
    }

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        final Thread.UncaughtExceptionHandler previous =
                Thread.getDefaultUncaughtExceptionHandler();
        Thread.setDefaultUncaughtExceptionHandler(
                new Thread.UncaughtExceptionHandler() {
            @Override
            public void uncaughtException(Thread t, Throwable e) {
                try {
                    Log.e(TAG, "java crash on " + t.getName(), e);
                    Activity a = mSingleton;
                    if (a != null) {
                        java.io.File dir = a.getExternalFilesDir(null);
                        if (dir != null) {
                            java.io.PrintWriter pw = new java.io.PrintWriter(
                                    new java.io.File(dir, "java-crash.txt"));
                            pw.println("java crash on thread " + t.getName());
                            e.printStackTrace(pw);
                            pw.close();
                        }
                    }
                } catch (Throwable ignored) {
                }
                if (previous != null) {
                    previous.uncaughtException(t, e);
                }
            }
        });
        super.onCreate(savedInstanceState);
    }
}
