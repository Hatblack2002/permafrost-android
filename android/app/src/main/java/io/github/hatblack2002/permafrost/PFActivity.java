package io.github.hatblack2002.permafrost;

import android.app.Activity;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.graphics.Color;
import android.graphics.Typeface;
import android.os.Bundle;
import android.util.Log;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import java.io.File;
import java.io.FileReader;

import java.util.concurrent.CountDownLatch;

import org.libsdl.app.SDLActivity;

/**
 * PFActivity — launcher subclass of SDL's SDLActivity for the Permafrost
 * Engine Android port.
 *
 * Rescue tool, not part of the game: on a correct boot nothing is shown
 * (no overlay, no window). It only surfaces boot failures:
 *
 *   (a) the engine returns a non-zero exit code — native code calls
 *       {@link #showBootReport} through JNI on the SDL thread; and
 *   (b) the previous run ended badly — a leftover boot-in-progress
 *       marker, a fatal-signal report or a Java crash file from the
 *       previous execution. Detection happens in {@link #onCreate},
 *       before the engine starts: the files are read, archived as
 *       {@code <name>.prev} so the report does not repeat, and the
 *       combined report is rendered on top of the starting engine with
 *       "Copiar registro" and "Cerrar" buttons.
 *
 * All screen text is in Spanish, like the rest of the rescue UI.
 */
public class PFActivity extends SDLActivity {

    private static final String TAG = "PFActivity";

    /** Report files live next to each other in the external files dir. */
    private static final String MARKER_FILE      = "boot-in-progress.marker";
    private static final String FATAL_FILE       = "boot-report-fatal.txt";
    private static final String JAVA_CRASH_FILE  = "java-crash.txt";
    private static final String LAST_REPORT_FILE = "boot-report.txt";

    /** Displayed-text cap (chars) so the report view stays responsive. */
    private static final int MAX_REPORT_CHARS = 65536;

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
                    View box = buildReportView(act,
                            "Permafrost — informe de arranque",
                            log,
                            new Runnable() {
                                @Override
                                public void run() {
                                    latch.countDown();
                                }
                            });
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

    /**
     * Builds the full-screen report box (dark background, monospace log,
     * "Copiar registro" + "Cerrar" buttons). {@code onClose} runs when
     * the user taps "Cerrar" — the caller decides whether that means
     * "release the blocked SDL thread" or "remove the overlay".
     */
    private static View buildReportView(final Activity act, String title,
            final String log, final Runnable onClose) {
        LinearLayout box = new LinearLayout(act);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setBackgroundColor(Color.rgb(12, 12, 16));
        box.setPadding(24, 24, 24, 24);

        TextView tvTitle = new TextView(act);
        tvTitle.setText(title);
        tvTitle.setTextColor(Color.rgb(255, 196, 96));
        tvTitle.setTypeface(Typeface.MONOSPACE, Typeface.BOLD);
        tvTitle.setTextSize(15);
        tvTitle.setPadding(0, 8, 0, 16);

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
        copy.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
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
        close.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View v) {
                onClose.run();
            }
        });

        buttons.addView(copy);
        buttons.addView(close);

        box.addView(tvTitle);
        box.addView(scroll, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f));
        box.addView(buttons, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT));
        return box;
    }

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        installJavaCrashHandler();

        // Case (b), checked BEFORE starting the engine (super.onCreate
        // wires SDL and onResume starts the native thread). The files are
        // read and archived here, before the native side can recreate or
        // truncate them, so the report is shown once and never repeats.
        final String previousReport = collectPreviousRunReport();

        super.onCreate(savedInstanceState);

        if (previousReport != null) {
            showPreviousRunReport(previousReport);
        }
    }

    private void installJavaCrashHandler() {
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
                        File dir = a.getExternalFilesDir(null);
                        if (dir != null) {
                            // Overwrite: keep only the last Java crash.
                            java.io.PrintWriter pw = new java.io.PrintWriter(
                                    new File(dir, JAVA_CRASH_FILE));
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
    }

    /**
     * Detects a previous bad run (marker, fatal report or Java crash
     * file), reads them, archives each shown file as {@code <name>.prev}
     * (replacing any older archive — only the last report is kept) and
     * returns the combined text. Returns null when the previous run did
     * not end badly, so a correct boot never shows anything.
     */
    private String collectPreviousRunReport() {
        try {
            File dir = getExternalFilesDir(null);
            if (dir == null) {
                return null;
            }
            File marker = new File(dir, MARKER_FILE);
            File fatal  = new File(dir, FATAL_FILE);
            File jcrash = new File(dir, JAVA_CRASH_FILE);

            boolean hasMarker = marker.isFile();
            boolean hasFatal  = fatal.isFile();
            boolean hasJava   = jcrash.isFile();
            if (!hasMarker && !hasFatal && !hasJava) {
                return null;
            }

            StringBuilder sb = new StringBuilder();
            sb.append("=== Permafrost — informe de la ejecución anterior ===\n");
            if (hasFatal) {
                sb.append("\n--- señal fatal (").append(FATAL_FILE)
                        .append(") ---\n");
                appendFileTail(sb, fatal);
                archiveReport(fatal);
            }
            if (hasJava) {
                sb.append("\n--- crash de Java (").append(JAVA_CRASH_FILE)
                        .append(") ---\n");
                appendFileTail(sb, jcrash);
                archiveReport(jcrash);
            }
            if (hasMarker) {
                sb.append("\n--- arranque sin completar (")
                        .append(MARKER_FILE).append(") ---\n");
                sb.append("La ejecución anterior terminó antes de dibujar ")
                        .append("un frame, sin señal fatal ni crash de ")
                        .append("Java capturado.\n");
                archiveReport(marker);
                File last = new File(dir, LAST_REPORT_FILE);
                if (last.isFile()) {
                    sb.append("\n--- último registro conocido (")
                            .append(LAST_REPORT_FILE).append(") ---\n");
                    appendFileTail(sb, last);
                    archiveReport(last);
                }
            }

            String text = sb.toString();
            if (text.length() > MAX_REPORT_CHARS) {
                text = "(…truncado…)\n"
                        + text.substring(text.length() - MAX_REPORT_CHARS);
            }
            return text;
        } catch (Throwable t) {
            Log.e(TAG, "collectPreviousRunReport failed", t);
            return null;
        }
    }

    /**
     * Appends at most MAX_REPORT_CHARS characters of the file to sb,
     * keeping the tail (the end of the file is where failures are).
     */
    private static void appendFileTail(StringBuilder sb, File f) {
        try {
            StringBuilder file = new StringBuilder();
            FileReader r = new FileReader(f);
            try {
                char[] buf = new char[8192];
                int n;
                while ((n = r.read(buf)) > 0) {
                    file.append(buf, 0, n);
                    if (file.length() > MAX_REPORT_CHARS) {
                        file.delete(0, file.length() - MAX_REPORT_CHARS);
                    }
                }
            } finally {
                r.close();
            }
            if (file.length() >= MAX_REPORT_CHARS) {
                sb.append("(…truncado…)\n");
            }
            sb.append(file);
        } catch (Throwable t) {
            sb.append("(no se pudo leer el archivo: ").append(t).append(")\n");
        }
    }

    /**
     * Archives one report file as {@code <name>.prev}, replacing any
     * older archive, so the report is shown only once per failure.
     */
    private static void archiveReport(File f) {
        try {
            File dst = new File(f.getParentFile(), f.getName() + ".prev");
            if (dst.exists() && !dst.delete()) {
                Log.w(TAG, "could not delete old archive " + dst);
            }
            if (!f.renameTo(dst)) {
                Log.w(TAG, "could not archive " + f);
            }
        } catch (Throwable t) {
            Log.w(TAG, "archive failed", t);
        }
    }

    /**
     * Renders the previous-run report on top of the starting engine.
     * "Cerrar" removes the overlay; the engine keeps running underneath.
     */
    private void showPreviousRunReport(final String log) {
        runOnUiThread(new Runnable() {
            @Override
            public void run() {
                try {
                    ViewGroup content = findViewById(android.R.id.content);
                    if (content == null) {
                        return;
                    }
                    final LinearLayout[] boxRef = new LinearLayout[1];
                    View box = buildReportView(PFActivity.this,
                            "Permafrost — informe de la ejecución anterior",
                            log,
                            new Runnable() {
                                @Override
                                public void run() {
                                    ViewGroup parent = boxRef[0] == null
                                            ? null
                                            : (ViewGroup) boxRef[0].getParent();
                                    if (parent != null) {
                                        parent.removeView(boxRef[0]);
                                    }
                                }
                            });
                    boxRef[0] = (LinearLayout) box;
                    content.addView(box, new ViewGroup.LayoutParams(
                            ViewGroup.LayoutParams.MATCH_PARENT,
                            ViewGroup.LayoutParams.MATCH_PARENT));
                } catch (Throwable t) {
                    Log.e(TAG, "failed to show previous-run report", t);
                }
            }
        });
    }
}
