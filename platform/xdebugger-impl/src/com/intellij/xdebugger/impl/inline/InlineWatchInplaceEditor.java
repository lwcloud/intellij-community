// Copyright 2000-2020 JetBrains s.r.o. Use of this source code is governed by the Apache 2.0 license that can be found in the LICENSE file.
package com.intellij.xdebugger.impl.inline;

import com.intellij.openapi.editor.Editor;
import com.intellij.openapi.project.Project;
import com.intellij.xdebugger.XDebugSession;
import com.intellij.xdebugger.XDebuggerManager;
import com.intellij.xdebugger.XExpression;
import com.intellij.xdebugger.XSourcePosition;
import com.intellij.xdebugger.impl.XDebuggerManagerImpl;
import com.intellij.xdebugger.impl.XDebuggerUtilImpl;
import com.intellij.xdebugger.impl.XDebuggerWatchesManager;
import com.intellij.xdebugger.impl.ui.InplaceEditor;
import com.intellij.xdebugger.impl.ui.XDebuggerExpressionComboBox;
import org.jetbrains.annotations.NotNull;

import javax.swing.*;
import java.awt.*;

public class InlineWatchInplaceEditor extends InplaceEditor {
  private final XSourcePosition myPosition;
  private final XDebugSession mySession;
  private final Editor myHostEditor;
  private XExpression myInitialExpression;
  private XDebuggerExpressionComboBox myInplaceEditor;

  public InlineWatchInplaceEditor(XSourcePosition position,
                                  @NotNull XDebugSession session,
                                  Editor editor) {
    this(position, session, editor, null);
  }

  public InlineWatchInplaceEditor(XSourcePosition position,
                                  @NotNull XDebugSession session,
                                  Editor editor,
                                  XExpression expression) {
    myPosition = position;
    mySession = session;
    myHostEditor = editor;
    myInitialExpression = expression;
  }

  @Override
  protected void beforeShow() { }

  @Override
  protected JComponent createInplaceEditorComponent() {
    myInplaceEditor = new XDebuggerExpressionComboBox(mySession.getProject(), mySession.getDebugProcess().getEditorsProvider(), "inlineWatch",
                                    myPosition, true, true);
    if (myInitialExpression != null) {
      myInplaceEditor.setExpression(myInitialExpression);
    }
    return myInplaceEditor.getComponent();
  }

  @Override
  protected JComponent getPreferredFocusedComponent() {
    return myInplaceEditor.getPreferredFocusedComponent();
  }

  @Override
  public Editor getEditor() {
    return myInplaceEditor.getEditor();
  }

  @Override
  public JComponent getEditorComponent() {
    return myInplaceEditor.getEditorComponent();
  }

  protected XExpression getExpression() {
    return myInplaceEditor.getExpression();
  }

  @Override
  public void doOKAction() {
    XExpression expression = getExpression();
    super.doOKAction();
    if (!XDebuggerUtilImpl.isEmptyExpression(expression)) {
      XDebuggerWatchesManager watchesManager = ((XDebuggerManagerImpl)XDebuggerManager.getInstance(mySession.getProject())).getWatchesManager();
      watchesManager.addInlineWatchExpression(expression, -1, myPosition, true);
    }
  }

  @Override
  public void cancelEditing() {
    super.cancelEditing();
    if (myInitialExpression != null) {
      XDebuggerWatchesManager watchesManager = ((XDebuggerManagerImpl)XDebuggerManager.getInstance(mySession.getProject())).getWatchesManager();
      watchesManager.addInlineWatchExpression(myInitialExpression, -1, myPosition, true);
    }
  }


  @Override
  protected JComponent getHostComponent() {
    return myHostEditor.getContentComponent();
  }


  @Override
  protected Project getProject() {
    return mySession.getProject();
  }

  @Override
  protected Rectangle getEditorBounds() {
    int caretOffset = myHostEditor.getCaretModel().getOffset();
    Point caretPoint = myHostEditor.offsetToXY(caretOffset);
    int width = myHostEditor.getContentComponent().getWidth() - (caretPoint.x - myHostEditor.getContentComponent().getX());
    int height = myHostEditor.getLineHeight();
    Rectangle bounds = myHostEditor.getContentComponent().getVisibleRect();
    Rectangle lineBounds = new Rectangle(caretPoint.x, caretPoint.y, width, height);
    if (bounds == null) {
      return null;
    }
    if (bounds.y > lineBounds.y || bounds.y + bounds.height < lineBounds.y + lineBounds.height) {
      return null;
    }
    bounds.y = lineBounds.y;
    bounds.height = lineBounds.height;

    if(lineBounds.x > bounds.x) {
      bounds.width = bounds.width - lineBounds.x + bounds.x;
      bounds.x = lineBounds.x;
    }
    return bounds;
  }
}
