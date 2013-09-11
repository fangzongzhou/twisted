# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Tests for L{twisted.tubes.tube}.
"""

from twisted.trial.unittest import TestCase
from twisted.tubes.test.util import (TesterPump, FakeFount,
                                     FakeDrain, IFakeInput)
from twisted.tubes.test.util import SwitchableTesterPump
from twisted.tubes.itube import ISwitchableTube, ISwitchablePump
from twisted.python.failure import Failure
from twisted.tubes.tube import Pump, series

from zope.interface import implementer


class ReprPump(Pump):
    def __repr__(self):
        return '<Pump For Testing>'



class PassthruPump(Pump):
    def received(self, data):
        yield data



class TubeTest(TestCase):
    """
    Tests for L{series}.
    """

    def setUp(self):
        """
        Create a tube, and a fake drain and fount connected to it.
        """
        self.pump = TesterPump()
        self.tubeDrain = series(self.pump)
        self.tube = self.pump.tube
        self.ff = FakeFount()
        self.fd = FakeDrain()


    def test_pumpAttribute(self):
        """
        The L{_Tube.pump} conveniently keeps L{Pump.tube} up to date when you
        set it.
        """
        firstPump = self.pump
        secondPump = Pump()
        self.assertIdentical(firstPump.tube, self.tube)
        self.assertIdentical(secondPump.tube, None)
        self.tube.pump = secondPump
        self.assertIdentical(firstPump.tube, None)
        self.assertIdentical(secondPump.tube, self.tube)


    def test_pumpStarted(self):
        """
        The L{_Tube} starts its L{Pump} upon C{flowingFrom}.
        """
        class Starter(Pump):
            def started(self):
                yield "greeting"

        self.ff.flowTo(series(Starter(), self.fd))
        self.assertEquals(self.fd.received, ["greeting"])


    def test_pumpStopped(self):
        """
        The L{_Tube} stops its L{Pump} upon C{flowStopped}.
        """
        reasons = []
        class Ender(Pump):
            def stopped(self, reason):
                reasons.append(reason)
                yield "conclusion"

        self.ff.flowTo(series(Ender(), self.fd))
        self.assertEquals(reasons, [])
        self.assertEquals(self.fd.received, [])
        self.ff.drain.flowStopped(Failure(ZeroDivisionError()))
        self.assertEquals(self.fd.received, ["conclusion"])
        self.assertEquals(len(reasons), 1)
        self.assertIdentical(reasons[0].type, ZeroDivisionError)


    def test_pumpFlowSwitching(self):
        """
        The L{_Tube} of a L{Pump} delivers data to a newly specified L{IDrain}
        when its L{ITube.switch} method is called.
        """
        @implementer(ISwitchablePump)
        class SwitchablePassthruPump(PassthruPump):
            def reassemble(self, data):
                return data

        sourcePump = SwitchablePassthruPump()
        fakeDrain = self.fd

        class Switcher(Pump):
            def received(self, data):
                if data == "switch":
                    sourcePump.tube.switch(series(Switchee(), fakeDrain))
                return ()

        class Switchee(Pump):
            def received(self, data):
                yield "switched " + data

        firstDrain = series(sourcePump)

        self.ff.flowTo(firstDrain).flowTo(series(Switcher(), fakeDrain))
        self.ff.drain.receive("switch")
        self.ff.drain.receive("to switchee")
        self.assertEquals(fakeDrain.received, ["switched to switchee"])


    def test_pumpFlowSwitching_WithCheese(self):
        # XXX RENAME
        """
        The L{_Tube} of a L{Pump} delivers reassembled data to a newly
        specified L{Drain}.
        """
        @implementer(ISwitchablePump)
        class ReassemblingPump(Pump):
            def received(self, datum):
                nonBorks = datum.split("BORK")
                return nonBorks

            def reassemble(self, data):
                for element in data:
                    yield 'BORK'
                    yield element

        class Switcher(Pump):
            def received(self, data):
                if data == "switch":
                    sourcePump.tube.switch(series(Switchee(), fakeDrain))
                return ()

        class Switchee(Pump):
            def received(self, data):
                yield "switched " + data

        sourcePump = ReassemblingPump()
        fakeDrain = self.fd
        firstDrain = series(sourcePump)
        self.ff.flowTo(firstDrain).flowTo(series(Switcher(), fakeDrain))

        self.ff.drain.receive("switchBORKto switchee")

        self.assertEquals(self.fd.received, ["switched BORK",
                                             "switched to switchee"])


    def test_pumpFlowSwitching_TheWorks(self):
        # XXX RENAME
        """
        Switching a pump that has never received data works I{just fine} thank
        you very much.
        """
        @implementer(ISwitchablePump)
        class SwitchablePassthruPump(PassthruPump):
            def reassemble(self, data):
                return data

        class Switcher(Pump):
            def received(self, data):
                if data == "switch":
                    destinationPump.tube.switch(series(Switchee(), fakeDrain))
                else:
                    return [data]

        class Switchee(Pump):
            def received(self, data):
                yield "switched " + data

        fakeDrain = self.fd
        destinationPump = SwitchablePassthruPump()

        firstDrain = series(Switcher(), destinationPump)
        self.ff.flowTo(firstDrain).flowTo(fakeDrain)
        self.ff.drain.receive("before")
        self.ff.drain.receive("switch")
        self.ff.drain.receive("after")
        self.assertEquals(self.fd.received, ["before", "switched after"])


    def test_flowingFromFirst(self):
        """
        If L{_Tube.flowingFrom} is called before L{_Tube.flowTo}, the argument
        to L{_Tube.flowTo} will immediately have its L{IDrain.flowingFrom}
        called.
        """
        self.ff.flowTo(self.tubeDrain).flowTo(self.fd)
        self.assertNotIdentical(self.fd.fount, None)


    def test_tubeReceiveCallsPumpReceived(self):
        """
        L{_TubeDrain.receive} will call C{pump.received} and synthesize a fake
        "0.5" progress result if L{None} is returned.
        """
        got = []
        class ReceivingPump(Pump):
            def received(self, item):
                got.append(item)
        self.tube.pump = ReceivingPump()
        self.tubeDrain.receive("sample item")
        self.assertEqual(got, ["sample item"])


    def test_tubeProgressRelaysPumpProgress(self):
        """
        L{_Tube.progress} will call L{Pump.progress}, and also call
        L{IDrain.progress}.
        """
        got = []
        class ProgressingPump(Pump):
            def progressed(self, amount=None):
                got.append(amount)
        self.tube.pump = ProgressingPump()
        self.assertEqual(got, [])
        self.tubeDrain.progress()
        self.tubeDrain.progress(0.6)
        self.assertEqual(got, [None, 0.6])


    def test_tubeReceiveRelaysProgressDownStream(self):
        """
        L{_TubeDrain.receive} will call its downstream L{IDrain}'s C{progress}
        method if its L{Pump} does not produce any output.
        """
        got = []
        class ProgressingPump(Pump):
            def progressed(self, amount=None):
                got.append(amount)
        self.ff.flowTo(self.tubeDrain).flowTo(series(ProgressingPump()))
        self.tubeDrain.receive(2)
        self.assertEquals(got, [None])


    def test_tubeReceiveDoesntRelayUnnecessaryProgress(self):
        """
        L{_TubeDrain.receive} will not call its downstream L{IDrain}'s
        C{progress} method if its L{Pump} I{does} produce some output, because
        the progress notification is redundant in that case; input was
        received, output was sent on.  A call to C{progress} would imply that
        I{more} data had come in, and that isn't necessarily true.
        """
        progged = []
        got = []
        class ReceivingPump(Pump):
            def received(self, item):
                yield item + 1
        class ProgressingPump(Pump):
            def progressed(self, amount=None):
                progged.append(amount)
            def received(self, item):
                got.append(item)
        self.tube.pump = ReceivingPump()
        self.ff.flowTo(self.tubeDrain).flowTo(series(ProgressingPump()))
        self.tubeDrain.receive(2)
        # sanity check
        self.assertEquals(got, [3])
        self.assertEquals(progged, [])


    def test_flowFromTypeCheck(self):
        """
        L{_Tube.flowingFrom} checks the type of its input.  If it doesn't match
        (both are specified explicitly, and they don't match).
        """
        class ToPump(Pump):
            inputType = IFakeInput
        self.tube.pump = ToPump()
        self.failUnlessRaises(TypeError, self.ff.flowTo, self.tubeDrain)


    def test_receiveIterableDeliversDownstream(self):
        """
        When L{Pump.received} yields a value, L{_Tube} will call L{receive} on
        its downstream drain.
        """
        self.ff.flowTo(series(PassthruPump())).flowTo(self.fd)
        self.ff.drain.receive(7)
        self.assertEquals(self.fd.received, [7])


    def test_deliverWaitsUntilThereIsADownstream(self):
        """
        L{_Tube.deliver} on a disconnected tube will buffer its input until
        there's an active drain to deliver to.
        """
        self.tube.deliver("hi")
        nextFount = self.ff.flowTo(self.tubeDrain)
        nextFount.flowTo(self.fd)
        self.assertEquals(self.fd.received, ["hi"])


    def test_deliverWithoutDownstreamPauses(self):
        """
        L{_Tube.deliver} on a tube with an upstream L{IFount} but no downstream
        L{IDrain} will pause its L{IFount}.  This is because the L{_Tube} has
        to buffer everything downstream, and it doesn't want to buffer
        infinitely; if it has nowhere to deliver onward to, then it issues a
        pause.  Note also that this happens when data is delivered via the
        L{_Tube} and I{not} when data arrives via the L{_Tube}'s C{receive}
        method, since C{receive} delivers onwards to the L{Pump} immediately,
        and does not require any buffering.
        """
        self.nextFount = self.ff.flowTo(self.tubeDrain)
        self.assertEquals(self.ff.flowIsPaused, False)
        self.tube.deliver("abc")
        self.assertEquals(self.ff.flowIsPaused, True)


    def test_preDeliveryPausesWhenUpstreamAdded(self):
        """
        If L{_Tube.deliver} has been called already (and the item it was called
        with is still buffered) when L{_Tube.flowingFrom} is called, it will
        pause the fount it is being added to.
        """
        self.tube.deliver('value')
        self.assertEqual(self.ff.flowIsPaused, False)
        self.ff.flowTo(self.tubeDrain)
        self.assertEqual(self.ff.flowIsPaused, True)


    def test_deliverPausesJustOnce(self):
        """
        L{_Tube.deliver} on a tube with an upstream L{IFount} will not call
        its C{pauseFlow} method twice.
        """
        self.test_deliverWithoutDownstreamPauses()
        self.tube.deliver("def")


    def test_addingDownstreamUnpauses(self):
        """
        When a L{_Tube} that is not flowing to a drain yet pauses its upstream
        fount, it will I{resume} its upstream fount when a new downstream
        arrives to un-buffer to.
        """
        self.test_deliverWithoutDownstreamPauses()
        self.nextFount.flowTo(self.fd)
        self.assertEquals(self.ff.flowIsPaused, False)


    def test_pauseFlowWhileUnbuffering(self):
        """
        When a L{_Tube} is unbuffering its inputs received while it didn't have
        a downstream drain, it may be interrupted by its downstream drain
        pausing it.

        If this happens, it should stop delivering.  It also shouldn't pause
        any upstream fount.
        """
        test = self
        class SlowDrain(FakeDrain):
            def __init__(self):
                super(SlowDrain, self).__init__()
                self.ready = True
            def receive(self, item):
                result = super(SlowDrain, self).receive(item)
                self.fount.pauseFlow()
                if not self.ready:
                    test.fail("Received twice.")
                self.ready = False
                return result
            def nextOne(self):
                self.ready = True
                self.fount.resumeFlow()
        sd = SlowDrain()
        nextFount = self.ff.flowTo(self.tubeDrain)
        # Buffer.
        self.tube.deliver(1)
        self.tube.deliver(2)
        self.tube.deliver(3)
        # Unbuffer.
        nextFount.flowTo(sd)
        self.assertEquals(sd.received, [1])
        sd.nextOne()
        self.assertEquals(sd.received, [1, 2])
        sd.nextOne()
        self.assertEquals(sd.received, [1, 2, 3])


    def test_receiveCallsPumpReceived(self):
        """
        L{_TubeDrain.receive} will deliver its input to L{IPump.received} on
        its pump.
        """
        self.tubeDrain.receive("one-item")
        self.assertEquals(self.tube.pump.allReceivedItems,
                          ["one-item"])


    def test_multiStageTubeReturnsLastStage(self):
        """
        XXX explain the way tubes hook together.
        """
        class A(Pump):
            pass
        class B(Pump):
            pass
        class C(Pump):
            pass
        a = A()
        b = B()
        c = C()
        ab = series(a, b, c)
        self.ff.flowTo(ab).flowTo(self.fd)
        a.tube.deliver("received by B")
        b.tube.deliver("receved by C")
        c.tube.deliver("received by FD")
        self.assertEquals(self.fd.received, ["received by FD"])


    def test_flowToWillNotResumeFlowPausedInFlowingFrom(self):
        """
        L{_TubeFount.flowTo} will not call L{_TubeFount.resumeFlow} when
        it's L{IDrain} calls L{IFount.pauseFlow} in L{IDrain.flowingFrom}.
        """
        class PausingDrain(FakeDrain):
            def flowingFrom(self, fount):
                self.fount = fount
                self.fount.pauseFlow()

        self.ff.flowTo(self.tubeDrain).flowTo(PausingDrain())

        self.assertTrue(self.ff.flowIsPaused, "Upstream is not paused.")


    def test_reentrantFlowTo(self):
        """
        An L{IDrain} may call its argument's L{_TubeFount.flowTo} method in
        L{IDrain.flowingFrom} and said fount will be flowing to the new drain.
        """
        test_fd = self.fd

        class ReflowingDrain(FakeDrain):
            def flowingFrom(self, fount):
                self.fount = fount
                self.fount.flowTo(test_fd)

        self.ff.flowTo(self.tubeDrain).flowTo(ReflowingDrain())

        self.assertIdentical(self.tube._tfount.drain, self.fd)

        self.tube.deliver("hello")
        self.assertEqual(self.fd.received, ["hello"])


    def test_drainPausesFlowWhenPreviouslyPaused(self):
        """
        L{_TubeDrain.flowingFrom} will pause its fount if its L{_TubeFount} was
        previously paused.
        """
        newFF = FakeFount()

        self.ff.flowTo(self.tubeDrain).pauseFlow()
        newFF.flowTo(self.tubeDrain)

        self.assertTrue(newFF.flowIsPaused, "New upstream is not paused.")


    def test_switchableTubeGetsImplemented(self):
        """
        Passing an L{ISwitchablePump} to L{_Tube} will cause it to implement
        L{ISwitchableTube}.
        """

        pump = SwitchableTesterPump()
        series(pump)
        self.assertTrue(ISwitchableTube.providedBy(pump.tube))


    def test_switchableTubeCanGetUnimplemented(self):
        """
        Passing an L{ISwitchablePump} and then a L{IPump} to L{_Tube} will
        cause it to no longer implement L{ISwitchableTube}.
        """

        pump = SwitchableTesterPump()
        series(pump)
        otherPump = TesterPump()
        tube = pump.tube
        tube.pump = otherPump
        self.assertFalse(ISwitchableTube.providedBy(tube))


    def test_switchableTubeCanStayImplemented(self):
        """
        Passing an L{ISwitchablePump} and then an L{ISwitchablePump} to
        L{_Tube} will cause it to still implement L{ISwitchableTube}.
        """

        pump = SwitchableTesterPump()
        series(pump)
        otherPump = SwitchableTesterPump()
        tube = pump.tube
        tube.pump = otherPump
        self.assertTrue(ISwitchableTube.providedBy(tube))


    def test_switchableTubeCanStayUnimplemented(self):
        """
        Passing an L{IPump} and then an L{IPump} to L{_Tube} will cause it to
        still not implement L{ISwitchableTube}.
        """

        pump = TesterPump()
        series(pump)
        otherPump = TesterPump()
        tube = pump.tube
        tube.pump = otherPump
        self.assertFalse(ISwitchableTube.providedBy(tube))


    def test_switchableTubeCanGetReimplemented(self):
        """
        Passing an L{ISwitchablePump} and then a L{IPump} and then an
        L{ISwitchablePump} again to L{_Tube} will cause it to implement
        L{ISwitchableTube}.
        """

        pump = SwitchableTesterPump()
        series(pump)
        otherPump = TesterPump()
        tube = pump.tube
        tube.pump = otherPump
        thirdPump = SwitchableTesterPump()
        tube.pump = thirdPump
        self.assertTrue(ISwitchableTube.providedBy(tube))


    def test_tubeDrainRepr(self):
        """
        repr for L{_TubeDrain} includes a reference to its pump.
        """

        self.assertEqual(repr(series(ReprPump())),
                         '<Drain for <Pump For Testing>>')


    def test_tubeFountRepr(self):
        """
        repr for L{_TubeFount} includes a reference to its pump.
        """

        fount = FakeFount()

        self.assertEqual(repr(fount.flowTo(series(ReprPump()))),
                         '<Fount for <Pump For Testing>>')


    def test_tubeRepr(self):
        """
        repr for L{_Tube} includes a reference to its pump.
        """

        pump = ReprPump()
        series(pump)

        self.assertEqual(repr(pump.tube), '<Tube for <Pump For Testing>>')
